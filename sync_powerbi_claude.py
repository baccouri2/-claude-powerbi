# -*- coding: utf-8 -*-
"""
sync_powerbi_claude.py
Synchronisation automatique Power BI Desktop → Claude (Render)
Toutes les 30 secondes, lit les données depuis Power BI Desktop
et les envoie au serveur Claude via /api/context
"""

import sys, os, time, json, requests
from datetime import datetime

# ── Configuration ─────────────────────────────────────────
CLAUDE_URL   = "https://claude-powerbi.onrender.com/api/context"
INTERVAL_SEC = 30   # intervalle de synchronisation en secondes

# ── Encodeur JSON sécurisé ─────────────────────────────────
class SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        from decimal import Decimal
        from datetime import date, datetime as dt
        if isinstance(obj, (date, dt)):   return str(obj)
        if isinstance(obj, Decimal):       return float(obj)
        try:    return super().default(obj)
        except: return str(obj)

def safe_json(data):
    return json.loads(json.dumps(data, cls=SafeEncoder))

# ── Lire données Power BI Desktop ─────────────────────────
def lire_powerbi():
    """Tente de lire depuis Power BI Desktop, sinon PostgreSQL"""
    try:
        # Ajouter le chemin DLL ADOMD
        dll = os.path.join(
            os.path.dirname(__file__),
            "adomd_lib", "lib", "net45",
            "Microsoft.AnalysisServices.AdomdClient.dll"
        )
        if os.path.exists(dll):
            from powerbi_direct import get_data_from_powerbi
            data = get_data_from_powerbi()
            source = "Power BI Desktop"
        else:
            raise ImportError("DLL ADOMD non trouvée")
    except Exception as e:
        # Fallback PostgreSQL
        from database import get_all_data
        data = get_all_data()
        source = "PostgreSQL (fallback)"
    return data, source

# ── Envoyer contexte à Claude ──────────────────────────────
def envoyer_contexte(data, source):
    """Envoie les données Power BI à Claude via /api/context"""
    k  = data.get("kpis", {})
    kp = data.get("kpis_prod", {})

    ctx = {
        "source"    : source,
        "timestamp" : datetime.now().strftime("%H:%M:%S"),
        "page"      : "all",
        "kpis"      : {
            "CA HT Total"        : f"{float(k.get('ca_ht', 0)):,.2f} DT",
            "Nb Commandes"       : int(k.get('nb_commandes', 0)),
            "Nb Clients"         : int(k.get('nb_clients', 0)),
            "Qte Vendue"         : int(k.get('qte_vendue', 0)),
            "Panier Moyen"       : f"{float(k.get('panier_moyen', 0)):,.2f} DT",
            "Marge Brute"        : f"{float(k.get('marge_brute', 0)):,.2f} DT",
            "Taux Marge"         : f"{float(k.get('taux_marge', 0)):.2f}%",
            "Taux Conversion"    : f"{float(k.get('taux_conversion', 0)):.2f}%",
            "Prix Moyen Produit" : f"{float(kp.get('prix_moyen', 0)):,.2f} DT",
            "Nb Distincts"       : int(kp.get('nb_distincts', 0)),
            "Qte Top Produit"    : int(kp.get('qte_top_produit', 0)),
            "Produits Non Vendus": int(kp.get('nb_non_vendus', 0)),
        },
        # Evolution CA par mois
        "evolution_ca" : [
            {"mois": m.get("mois_nom", ""), "ca": f"{float(m.get('ca_ht', 0)):,.2f} DT"}
            for m in data.get("evolution_ca", [])
        ],
        # Top 5 clients
        "top_clients" : [
            {"client": c.get("client", ""), "ca": f"{float(c.get('ca_ht', 0)):,.2f} DT",
             "pct": f"{float(c.get('pct_ca', 0)):.1f}%"}
            for c in data.get("clients", [])[:5]
        ],
        # Top 5 catégories
        "top_categories" : [
            {"categorie": c.get("categorie", ""),
             "ca": f"{float(c.get('ca_ht', 0)):,.2f} DT",
             "pct": f"{float(c.get('pct_ca', 0)):.1f}%"}
            for c in data.get("categories", [])[:5]
        ],
        # Top 5 produits
        "top_produits" : [
            {"produit": p.get("produit", ""),
             "ca": f"{float(p.get('ca_ht', 0)):,.2f} DT",
             "qte": int(p.get("qte_vendue", 0))}
            for p in data.get("top10_ca", [])[:5]
        ],
    }

    try:
        resp = requests.post(
            CLAUDE_URL,
            json    = safe_json(ctx),
            timeout = 15,
            headers = {"Content-Type": "application/json"}
        )
        if resp.status_code == 200:
            return True, resp.json()
        else:
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)

# ── Comparer deux snapshots de KPIs ───────────────────────
def kpis_changes(old, new):
    """Retourne True si les KPIs ont changé"""
    if not old or not new:
        return True
    ok  = old.get("kpis", {})
    nk  = new.get("kpis", {})
    return (ok.get("ca_ht") != nk.get("ca_ht") or
            ok.get("nb_commandes") != nk.get("nb_commandes") or
            ok.get("nb_clients") != nk.get("nb_clients"))

# ── Boucle principale ──────────────────────────────────────
def main():
    print("=" * 60)
    print("  SYNC Power BI Desktop → Claude (Render)")
    print(f"  URL : {CLAUDE_URL}")
    print(f"  Intervalle : {INTERVAL_SEC} secondes")
    print("  Ctrl+C pour arrêter")
    print("=" * 60)

    dernier_snapshot = None
    nb_syncs = 0

    while True:
        try:
            heure = datetime.now().strftime("%H:%M:%S")

            # Lire les données
            data, source = lire_powerbi()

            # Vérifier si les données ont changé
            changement = kpis_changes(dernier_snapshot, data)

            if changement or nb_syncs == 0:
                # Envoyer à Claude
                ok, resultat = envoyer_contexte(data, source)
                nb_syncs += 1

                k = data.get("kpis", {})
                ca    = float(k.get("ca_ht", 0))
                cmdes = int(k.get("nb_commandes", 0))

                if ok:
                    status = "✅ Sync OK"
                    if changement and dernier_snapshot:
                        status += " (DONNÉES MISES À JOUR)"
                else:
                    status = f"❌ Erreur: {resultat}"

                print(f"[{heure}] {status} | Source: {source} | CA: {ca:,.2f} DT | Cmdes: {cmdes}")
                dernier_snapshot = data
            else:
                print(f"[{heure}] ⏸  Pas de changement — prochain check dans {INTERVAL_SEC}s")

        except KeyboardInterrupt:
            print("\n\n⛔ Synchronisation arrêtée.")
            break
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️  Erreur: {e}")

        time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    main()
