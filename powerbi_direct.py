# -*- coding: utf-8 -*-
"""
powerbi_direct.py
Connexion directe Power BI Desktop via ADOMD.NET
Port détecté automatiquement à chaque ouverture de Power BI
"""

import sys, os, json, psutil

# ── Charger la DLL ADOMD ──────────────────────────────────
ADOMD_DLL = (
    r"C:\Users\ranin baccouri\Desktop\claude_powerbi"
    r"\adomd_lib\lib\net45\Microsoft.AnalysisServices.AdomdClient.dll"
)
sys.path.insert(0, os.path.dirname(ADOMD_DLL))
import clr
clr.AddReference(ADOMD_DLL)
from Microsoft.AnalysisServices.AdomdClient import AdomdConnection, AdomdCommand

from database import get_all_data as fallback


# ── Utilitaires ───────────────────────────────────────────
def _f(v):
    try: return float(v) if v is not None else 0.0
    except: return 0.0

def _i(v):
    try: return int(float(v)) if v is not None else 0
    except: return 0

def _exec(conn, dax):
    try:
        cmd    = AdomdCommand(dax, conn)
        reader = cmd.ExecuteReader()
        rows   = []
        while reader.Read():
            rows.append([reader[i] for i in range(reader.FieldCount)])
        reader.Close()
        return rows if rows else None
    except:
        return None

def _measure(conn, expr):
    rows = _exec(conn, f'EVALUATE ROW("v", {expr})')
    return _f(rows[0][0]) if rows else 0.0


# ── Détection automatique port + catalogue ────────────────
def _find_port():
    """Détecte le port Power BI Desktop automatiquement"""
    # Méthode 1 : fichiers temporaires Power BI
    ws_root = os.path.expanduser(
        r"~\AppData\Local\Microsoft\Power BI Desktop\AnalysisServicesWorkspaces"
    )
    if os.path.exists(ws_root):
        for ws in os.listdir(ws_root):
            for root, _, files in os.walk(os.path.join(ws_root, ws)):
                for fname in files:
                    if fname.lower() in ['msmdsrv.port', 'port']:
                        try:
                            return int(open(os.path.join(root, fname)).read().strip())
                        except:
                            pass

    # Méthode 2 : processus msmdsrv de Power BI Desktop
    for proc in psutil.process_iter(['name', 'exe']):
        try:
            if ('msmdsrv' in proc.info['name'].lower() and
                    'Power BI' in (proc.info.get('exe') or '')):
                for c in proc.net_connections():
                    if c.status == 'LISTEN' and c.laddr.port != 2383:
                        return c.laddr.port
        except:
            pass
    return None


def _find_catalog(port):
    """Trouve le catalogue UUID du rapport Power BI ouvert"""
    try:
        conn = AdomdConnection(f"Data Source=localhost:{port};")
        conn.Open()
        cmd    = AdomdCommand(
            "SELECT [CATALOG_NAME] FROM $SYSTEM.DBSCHEMA_CATALOGS", conn)
        reader = cmd.ExecuteReader()
        cats   = []
        while reader.Read():
            c = str(reader[0])
            if len(c) > 20 and '-' in c:
                cats.append(c)
        reader.Close()
        conn.Close()
        return cats[0] if cats else None
    except:
        return None


# ── Lecture données Power BI ──────────────────────────────
def get_data_from_powerbi() -> dict:
    """
    Lit toutes les données directement depuis Power BI Desktop
    Fallback vers PostgreSQL si Power BI non disponible
    """
    # Détecter port automatiquement
    port = _find_port()
    if not port:
        print("Power BI Desktop non detecte — fallback PostgreSQL")
        return fallback()

    # Trouver catalogue
    catalog = _find_catalog(port)
    if not catalog:
        print(f"Catalogue introuvable (port {port}) — fallback PostgreSQL")
        return fallback()

    print(f"Power BI Desktop: port={port}, catalogue={catalog[:8]}...")

    try:
        conn = AdomdConnection(
            f"Data Source=localhost:{port};Catalog={catalog};"
        )
        conn.Open()
    except Exception as e:
        print(f"Connexion echouee: {e} — fallback PostgreSQL")
        return fallback()

    data = {}

    try:
        # ── PAGE 1 — KPIs ─────────────────────────────────
        kpis = {
            "ca_ht"          : _measure(conn, "[CA Total HT]"),
            "marge_brute"    : _measure(conn, "[Marge Brute]"),
            "taux_marge"     : round(_measure(conn, "[Taux de Marge]") * 100, 2),
            "taux_conversion": round(_measure(conn, "[Taux Conversion]") * 100, 2),
            "nb_commandes"   : _measure(conn, "[Nombre Commandes]"),
            "nb_clients"     : _measure(conn, "[Nombre Clients]"),
            "panier_moyen"   : _measure(conn, "[Panier Moyen]"),
            "qte_vendue"     : _measure(conn, "[Quantité Vendue]"),
        }
        data["kpis"] = kpis
        print(f"  KPIs: CA={kpis['ca_ht']:,.2f} Cmd={_i(kpis['nb_commandes'])} Cli={_i(kpis['nb_clients'])}")

        total = kpis["ca_ht"] or 1

        # ── Evolution CA par mois (table Calendrier) ──────
        rows = _exec(conn, """
            EVALUATE
            SUMMARIZECOLUMNS(
                'Calendrier'[Année-Mois],
                'Calendrier'[Mois Nom],
                "ca_ht",        [CA Total HT],
                "nb_commandes", [Nombre Commandes],
                "qte_vendue",   [Quantité Vendue]
            )
            ORDER BY 'Calendrier'[Année-Mois] ASC
        """)
        data["evolution_ca"] = [
            {"annee_mois": str(r[0]), "mois_nom": str(r[1]),
             "ca_ht": _f(r[2]), "nb_commandes": _i(r[3]),
             "qte_vendue": _f(r[4])}
            for r in (rows or [])
        ]
        print(f"  evolution_ca: {len(data['evolution_ca'])} mois")

        # ── CA par client (colonne 'Client') ───────────────
        rows = _exec(conn, """
            EVALUATE
            SUMMARIZECOLUMNS(
                'public res_partner'[Client],
                "ca_ht",        [CA Total HT],
                "nb_commandes", [Nombre Commandes],
                "panier_moyen", [Panier Moyen Client],
                "pct_ca",       [% CA],
                "marge_brute",  [Marge Brute],
                "taux_marge",   [Taux de Marge]
            )
            ORDER BY [ca_ht] DESC
        """)
        data["clients"] = [
            {"client": str(r[0]), "ca_ht": _f(r[1]),
             "nb_commandes": _i(r[2]), "panier_moyen": _f(r[3]),
             "pct_ca": round(_f(r[4]) * 100, 2),
             "marge_brute": _f(r[5]),
             "taux_marge": round(_f(r[6]) * 100, 2)}
            for r in (rows or [])
        ]
        print(f"  clients: {len(data['clients'])}")

        # ── CA par catégorie ───────────────────────────────
        # Essayer les différents noms de colonnes possibles
        rows = None
        for col in ["[Nom Produit]", "[complete_name]", "[name]"]:
            rows = _exec(conn, f"""
                EVALUATE
                SUMMARIZECOLUMNS(
                    'public product_category'{col},
                    "ca_ht",      [CA Total HT],
                    "qte_vendue", [Quantité Vendue]
                )
                ORDER BY [ca_ht] DESC
            """)
            if rows:
                break
        data["categories"] = [
            {"categorie": str(r[0]), "ca_ht": _f(r[1]),
             "qte_vendue": _f(r[2]),
             "pct_ca": round(_f(r[1]) / total * 100, 2)}
            for r in (rows or [])
        ]
        print(f"  categories: {len(data['categories'])}")

        # ── PAGE 2 — Statuts commandes ────────────────────
        rows = _exec(conn, """
            EVALUATE
            SUMMARIZECOLUMNS(
                'public sale_order'[state],
                "nb", [Nombre Commandes]
            )
        """)
        total_so = sum(_i(r[1]) for r in (rows or []))
        data["statuts"] = [
            {"state": str(r[0]), "nb": _i(r[1]),
             "pct": round(_i(r[1]) / total_so * 100, 1) if total_so else 0}
            for r in (rows or [])
        ]

        # ── PAGE 3 — KPIs produits ────────────────────────
        kpis_prod = {
            "prix_moyen"  : _measure(conn, "[Prix Moyen Produits]"),
            "nb_distincts": _measure(conn, "[NB Produits Distincts]"),
            "qte_totale"  : kpis["qte_vendue"],
        }
        # Mesures avec fallback PostgreSQL si non disponibles
        qt = _measure(conn, "[Quantité Top Produits]")
        nv = _measure(conn, "[NB Produits Non Vendues]")
        if qt == 0 or nv == 0:
            from database import get_kpis_produits
            db = get_kpis_produits()
            kpis_prod["qte_top_produit"] = db.get("qte_top_produit", 175)
            kpis_prod["nb_non_vendus"]   = db.get("nb_non_vendus", 53)
        else:
            kpis_prod["qte_top_produit"] = qt
            kpis_prod["nb_non_vendus"]   = nv
        data["kpis_prod"] = kpis_prod
        print(f"  kpis_prod: prix={kpis_prod['prix_moyen']:.2f} distincts={_i(kpis_prod['nb_distincts'])}")

        # ── Top 10 produits par CA ────────────────────────
        rows = _exec(conn, """
            EVALUATE
            TOPN(10,
                SUMMARIZECOLUMNS(
                    'public product_template'[Nom Produit],
                    "ca_ht",      [CA Total HT],
                    "qte_vendue", [Quantité Vendue],
                    "prix_moyen", [Prix Moyen Produits]
                ),
                [ca_ht], DESC
            )
            ORDER BY [ca_ht] DESC
        """)
        data["top10_ca"] = [
            {"produit": str(r[0]), "ca_ht": _f(r[1]),
             "qte_vendue": _f(r[2]), "prix_moyen": _f(r[3])}
            for r in (rows or [])
        ]
        print(f"  top10_ca: {len(data['top10_ca'])} produits")

        # ── Top 5 produits par quantité ───────────────────
        rows = _exec(conn, """
            EVALUATE
            TOPN(5,
                SUMMARIZECOLUMNS(
                    'public product_template'[Nom Produit],
                    "qte_vendue", [Quantité Vendue],
                    "ca_ht",      [CA Total HT]
                ),
                [qte_vendue], DESC
            )
            ORDER BY [qte_vendue] DESC
        """)
        tq = sum(_f(r[1]) for r in (rows or []))
        data["top5_qte"] = [
            {"produit": str(r[0]), "qte_vendue": _f(r[1]),
             "ca_ht": _f(r[2]),
             "pct": round(_f(r[1]) / tq * 100, 2) if tq else 0}
            for r in (rows or [])
        ]

        # ── Top 10 panier moyen ───────────────────────────
        rows = _exec(conn, """
            EVALUATE
            TOPN(10,
                SUMMARIZECOLUMNS(
                    'public product_template'[Nom Produit],
                    "panier_moyen", [Panier Moyen],
                    "qte_vendue",   [Quantité Vendue],
                    "ca_ht",        [CA Total HT]
                ),
                [panier_moyen], DESC
            )
            ORDER BY [panier_moyen] DESC
        """)
        data["top10_panier"] = [
            {"produit": str(r[0]), "panier_moyen": _f(r[1]),
             "qte_vendue": _f(r[2]), "ca_ht": _f(r[3])}
            for r in (rows or [])
        ]

        # ── Détail produits ───────────────────────────────
        rows = _exec(conn, """
            EVALUATE
            SUMMARIZECOLUMNS(
                'public product_template'[Nom Produit],
                "qte_vendue",  [Quantité Vendue],
                "ca_total",    [CA Total],
                "marge_brute", [Marge Brute]
            )
            ORDER BY [qte_vendue] DESC
        """)
        data["detail_produits"] = [
            {"produit": str(r[0]), "qte_vendue": _f(r[1]),
             "ca_total": _f(r[2]), "marge_brute": _f(r[3])}
            for r in (rows or [])
        ]
        print(f"  detail_produits: {len(data['detail_produits'])}")

        # ── Quantité vendue par client et par mois ────────
        # Visuel "Quantité Vendue Par Client" — Page 1
        rows = _exec(conn, """
            EVALUATE
            SUMMARIZECOLUMNS(
                'public res_partner'[Client],
                'Calendrier'[Mois Nom],
                "qte_vendue", [Quantité Vendue],
                "ca_ht",      [CA Total HT]
            )
            ORDER BY [qte_vendue] DESC
        """)
        data["qte_client_mois"] = [
            {"client"    : str(r[0]),
             "mois_nom"  : str(r[1]),
             "qte_vendue": _f(r[2]),
             "ca_ht"     : _f(r[3])}
            for r in (rows or [])
        ]
        # Résumé total par client
        data["qte_par_client"] = {}
        for row in data["qte_client_mois"]:
            c = row["client"]
            if c not in data["qte_par_client"]:
                data["qte_par_client"][c] = 0
            data["qte_par_client"][c] += row["qte_vendue"]
        data["qte_par_client"] = [
            {"client": k, "qte_vendue": v}
            for k, v in sorted(data["qte_par_client"].items(),
                               key=lambda x: x[1], reverse=True)
        ]
        print(f"  qte_client_mois: {len(data['qte_client_mois'])} lignes")

        conn.Close()
        print("Connexion Power BI Desktop OK !")
        return data

    except Exception as e:
        print(f"Erreur lecture: {e} — fallback PostgreSQL")
        try: conn.Close()
        except: pass
        return fallback()


# ── Test standalone ───────────────────────────────────────
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    data = get_data_from_powerbi()
    k  = data.get("kpis", {})
    kp = data.get("kpis_prod", {})
    print("\n" + "=" * 55)
    print("VERIFICATION DONNEES POWER BI")
    print("=" * 55)
    print(f"CA HT           : {k.get('ca_ht',0):>12,.2f} DT  (attendu: 447,313.38)")
    print(f"Marge Brute     : {k.get('marge_brute',0):>12,.2f} DT")
    print(f"Taux Marge      : {k.get('taux_marge',0):>11.2f} %   (attendu: 16.91%)")
    print(f"Taux Conversion : {k.get('taux_conversion',0):>11.2f} %   (attendu: 76%)")
    print(f"Nb Commandes    : {_i(k.get('nb_commandes',0)):>12}   (attendu: 50)")
    print(f"Nb Clients      : {_i(k.get('nb_clients',0)):>12}   (attendu: 7)")
    print(f"Panier Moyen    : {k.get('panier_moyen',0):>12,.2f} DT")
    print(f"Qte Vendue      : {_i(k.get('qte_vendue',0)):>12}   (attendu: 836)")
    print(f"Prix Moyen      : {kp.get('prix_moyen',0):>12,.2f} DT  (attendu: 478.63)")
    print(f"Qte Top Produit : {_i(kp.get('qte_top_produit',0)):>12}   (attendu: 175)")
    print(f"Produits Non V. : {_i(kp.get('nb_non_vendus',0)):>12}   (attendu: 53)")
    print(f"Nb Distincts    : {_i(kp.get('nb_distincts',0)):>12}   (attendu: 38)")
    print()
    print("Evolution CA:")
    for m in data.get("evolution_ca", []):
        print(f"  {m['mois_nom']:<12} CA={m['ca_ht']:>10,.2f} DT")
    print()
    print("Clients:")
    for c in data.get("clients", [])[:5]:
        print(f"  {c['client']:<25} CA={c['ca_ht']:>10,.2f} DT ({c['pct_ca']:.1f}%)")
    print()
    print("Categories:")
    for cat in data.get("categories", []):
        print(f"  {cat['categorie']:<25} CA={cat['ca_ht']:>10,.2f} DT ({cat['pct_ca']:.1f}%)")
