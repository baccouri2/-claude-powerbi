"""
app.py — Serveur Flask
Fonctionne en local (Power BI Direct) et sur Render (PostgreSQL)
"""

from flask import Flask, render_template, request, jsonify
from claude_agent import chat
from config import PORT, DEBUG
import os, threading
from datetime import datetime, timezone, timedelta

# Fuseau horaire Tunisie = UTC+1
TZ_TUNISIE = timezone(timedelta(hours=1))

def now_tunisie():
    return datetime.now(TZ_TUNISIE).strftime("%H:%M:%S")

app = Flask(__name__)
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
@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/")
def index():
    return render_template("index.html")

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
        result = chat(question + page_context.get(page, ""), historique, data)
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
