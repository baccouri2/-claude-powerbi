"""
app.py — Serveur Flask
Fonctionne en local (Power BI Direct) et sur Render (PostgreSQL)
"""

from flask import Flask, render_template, request, jsonify
from flask.json.provider import DefaultJSONProvider
from claude_agent import chat
from config import PORT, DEBUG
import os, threading, json, time, requests as _requests
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal

# ── Contexte Power BI partagé (mis à jour par /api/context) ──
_pbi_context = {}
_pbi_context_lock = threading.Lock()

# Fuseau horaire Tunisie = UTC+1
TZ_TUNISIE = timezone(timedelta(hours=1))

def now_tunisie():
    return datetime.now(TZ_TUNISIE).strftime("%H:%M:%S")

# ── Encodeur JSON — convertit date et Decimal ─────────────
class SafeJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

app = Flask(__name__)
app.json_provider_class = SafeJSONProvider
app.json = SafeJSONProvider(app)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# ── Source de données selon l'environnement ───────────────
def get_data():
    """
    Local  : Power BI Desktop direct (ADOMD.NET)
    Render : PostgreSQL Odoo (fallback)
    """
    # Sur Render, pas de Power BI Desktop → PostgreSQL direct
    if os.environ.get("RENDER"):
        from database import get_all_data
        return get_all_data()

    # En local → Power BI Desktop direct
    try:
        from powerbi_direct import get_data_from_powerbi
        return get_data_from_powerbi()
    except Exception:
        from database import get_all_data
        return get_all_data()

# ── Synchronisation (local uniquement) ───────────────────
if not os.environ.get("RENDER"):
    try:
        import sync_watcher
        sync_watcher.start(interval=10)

        def on_change(old, new):
            k_old = old.get("kpis", {})
            k_new = new.get("kpis", {})
            if k_old.get("ca_ht") != k_new.get("ca_ht"):
                print(f"[Sync] CA: {k_old.get('ca_ht',0):,.2f} → {k_new.get('ca_ht',0):,.2f} DT")
        sync_watcher.on_change(on_change)
        print("Synchronisation Power BI active (10s)")
    except Exception as e:
        print(f"Sync non disponible : {e}")

# ── Routes ────────────────────────────────────────────────
@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": now_tunisie()})

@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/context", methods=["POST", "OPTIONS"])
def api_context():
    """
    Reçoit le contexte Power BI (filtres actifs, client sélectionné, page, etc.)
    Appelé depuis le visuel HTML Power BI quand l'utilisateur change une sélection.
    """
    if request.method == "OPTIONS":
        resp = jsonify({"ok": True})
        resp.headers["Access-Control-Allow-Origin"]  = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return resp

    try:
        ctx = request.json or {}
        with _pbi_context_lock:
            _pbi_context.clear()
            _pbi_context.update({
                "client"    : ctx.get("client", ""),
                "categorie" : ctx.get("categorie", ""),
                "mois"      : ctx.get("mois", ""),
                "page"      : ctx.get("page", ""),
                "ca"        : ctx.get("ca", ""),
                "kpis"      : ctx.get("kpis", {}),
                "timestamp" : now_tunisie()
            })
        print(f"[PBI Contexte] reçu : {_pbi_context}")
        resp = jsonify({"success": True, "context": _pbi_context})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp
    except Exception as e:
        resp = jsonify({"success": False, "error": str(e)})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, 500

@app.route("/api/context", methods=["GET"])
def api_context_get():
    """Retourne le contexte Power BI actuel"""
    with _pbi_context_lock:
        ctx = dict(_pbi_context)
    resp = jsonify(ctx)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

@app.route("/api/kpis")
def api_kpis():
    try:
        data = get_data()
        k    = data.get("kpis", {})
        kp   = data.get("kpis_prod", {})
        return jsonify({
            "ca_ht"           : k.get("ca_ht", 0),
            "marge_brute"     : k.get("marge_brute", 0),
            "taux_marge"      : k.get("taux_marge", 0),
            "taux_conversion" : k.get("taux_conversion", 0),
            "nb_commandes"    : k.get("nb_commandes", 0),
            "nb_clients"      : k.get("nb_clients", 0),
            "panier_moyen"    : k.get("panier_moyen", 0),
            "qte_vendue"      : k.get("qte_vendue", 0),
            "date_debut"      : str(k.get("date_debut", "")),
            "date_fin"        : str(k.get("date_fin", "")),
            "nb_distincts"    : kp.get("nb_distincts", 0),
            "prix_moyen"      : kp.get("prix_moyen", 0),
            "qte_top_produit" : kp.get("qte_top_produit", 0),
            "nb_non_vendus"   : kp.get("nb_non_vendus", 0),
            "last_sync"       : now_tunisie()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        body       = request.json or {}
        question   = body.get("question", "").strip()
        historique = body.get("historique", [])
        page       = body.get("page", "all")

        if not question:
            return jsonify({"success": False, "response": "Question vide."}), 400

        data = get_data()
        page_context = {
            "page1": " (Page 1 — Vue Generale)",
            "page2": " (Page 2 — Analyse Commerciale)",
            "page3": " (Page 3 — Analyse Produits)",
            "all"  : ""
        }
        # Injecter le contexte Power BI actif dans la question
        with _pbi_context_lock:
            pbi_ctx = dict(_pbi_context)
        result = chat(question + page_context.get(page, ""), historique, data, pbi_ctx)
        return jsonify(result)

    except Exception as e:
        print(f"Erreur /api/chat : {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success" : False,
            "response": f"❌ Erreur serveur : {str(e)}"
        }), 500

if __name__ == "__main__":
    print("=" * 60)
    print("  CLAUDE AI — RAPPORT POWER BI 'stage bi'")
    print(f"  URL : http://localhost:{PORT}")
    print("=" * 60)
    app.run(debug=DEBUG, port=PORT, host="0.0.0.0")

# ── Keep-alive sur Render (évite le cold start) ───────────
def _keep_alive():
    """Ping le serveur toutes les 10 minutes pour éviter l'endormissement"""
    time.sleep(60)  # attendre 1 minute au démarrage
    url = os.environ.get("RENDER_EXTERNAL_URL", "https://claude-powerbi.onrender.com")
    while True:
        try:
            _requests.get(f"{url}/health", timeout=10)
            print(f"[Keep-alive] ping OK — {now_tunisie()}")
        except Exception as e:
            print(f"[Keep-alive] erreur : {e}")
        time.sleep(600)  # toutes les 10 minutes

if os.environ.get("RENDER"):
    _t = threading.Thread(target=_keep_alive, daemon=True)
    _t.start()
    print("Keep-alive démarré (ping toutes les 10 min)")
