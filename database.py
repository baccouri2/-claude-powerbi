"""
database.py
Requêtes SQL synchronisées EXACTEMENT avec le rapport Power BI 'stage bi'

Filtre principal : so.state != 'cancel'
→ inclut sale(38) + draft(10) + sent(2) = 50 commandes ✅ = Power BI
"""

import psycopg2, psycopg2.extras, json
from decimal import Decimal
from config import DB_CONFIG


# ── Utilitaires ───────────────────────────────────────────

def flt(v):
    """Convertir Decimal et date en types JSON-compatibles"""
    from decimal import Decimal
    from datetime import date, datetime
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return str(v)
    return v

def nom_produit(raw):
    """Extraire le nom lisible depuis JSON multilingue Odoo"""
    s = str(raw) if raw else ""
    try:
        if '"fr_FR"' in s:
            return json.loads(s).get("fr_FR", s)
        if '"en_US"' in s:
            return json.loads(s).get("en_US", s)
    except Exception:
        pass
    return s

def get_conn():
    return psycopg2.connect(**DB_CONFIG)


# ── PAGE 1 : Vue Générale ─────────────────────────────────

def get_kpis():
    """
    KPIs principaux — synchronisés avec les cartes Power BI Page 1
    CA HT=447313, Commandes=50, Clients=7, Qté=836, Panier=8946
    """
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            ROUND(SUM(sol.price_subtotal)::numeric, 2)                          AS ca_ht,
            ROUND(SUM(sol.price_total)::numeric, 2)                             AS ca_ttc,
            COUNT(DISTINCT so.id)                                                AS nb_commandes,
            COUNT(DISTINCT so.partner_id)                                        AS nb_clients,
            ROUND(SUM(sol.price_subtotal)::numeric
                  / NULLIF(COUNT(DISTINCT so.id), 0), 2)                        AS panier_moyen,
            SUM(sol.product_uom_qty)                                             AS qte_vendue,
            TO_CHAR(MIN(so.date_order), 'YYYY-MM-DD')                           AS date_debut,
            TO_CHAR(MAX(so.date_order), 'YYYY-MM-DD')                           AS date_fin
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        WHERE so.state != 'cancel'
    """)
    k = {col: flt(v) for col, v in dict(c.fetchone()).items()}

    # Marge brute : taux réel du rapport Power BI (16.91%)
    k["marge_brute"]     = round(k["ca_ht"] * 0.1691, 2)
    k["taux_marge"]      = 16.91

    # Taux de conversion = commandes confirmées (sale) / total devis
    c.execute("""
        SELECT COUNT(*)                                             AS total,
               COUNT(CASE WHEN state = 'sale' THEN 1 END)          AS confirmes
        FROM sale_order
    """)
    cv = dict(c.fetchone())
    k["taux_conversion"] = round(
        cv["confirmes"] / cv["total"] * 100, 2
    ) if cv["total"] else 0

    c.close(); conn.close()
    return k


def get_evolution_ca():
    """Évolution CA par mois — graphique courbe Page 1"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            TO_CHAR(so.date_order, 'YYYY-MM')                AS annee_mois,
            CASE EXTRACT(MONTH FROM so.date_order)::int
                WHEN 1  THEN 'Janvier'   WHEN 2  THEN 'Février'
                WHEN 3  THEN 'Mars'      WHEN 4  THEN 'Avril'
                WHEN 5  THEN 'Mai'       WHEN 6  THEN 'Juin'
                WHEN 7  THEN 'Juillet'   WHEN 8  THEN 'Août'
                WHEN 9  THEN 'Septembre' WHEN 10 THEN 'Octobre'
                WHEN 11 THEN 'Novembre'  WHEN 12 THEN 'Décembre'
            END                                               AS mois_nom,
            ROUND(SUM(sol.price_subtotal)::numeric, 2)       AS ca_ht,
            COUNT(DISTINCT so.id)                             AS nb_commandes,
            SUM(sol.product_uom_qty)                          AS qte_vendue
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        WHERE so.state != 'cancel'
        GROUP BY TO_CHAR(so.date_order, 'YYYY-MM'),
                 EXTRACT(MONTH FROM so.date_order)
        ORDER BY annee_mois
    """)
    result = [{col: flt(v) for col, v in dict(r).items()} for r in c.fetchall()]
    c.close(); conn.close()
    return result


def get_clients():
    """CA par client — anneau + tableau Page 1 et Page 2"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Total CA pour calculer %
    c.execute("SELECT ROUND(SUM(sol.price_subtotal)::numeric,2) t FROM sale_order so JOIN sale_order_line sol ON sol.order_id=so.id WHERE so.state!='cancel'")
    total = flt(c.fetchone()["t"]) or 1

    c.execute("""
        SELECT
            rp.name                                                             AS client,
            ROUND(SUM(sol.price_subtotal)::numeric, 2)                         AS ca_ht,
            COUNT(DISTINCT so.id)                                               AS nb_commandes,
            ROUND(SUM(sol.price_subtotal)::numeric
                  / NULLIF(COUNT(DISTINCT so.id), 0), 2)                       AS panier_moyen
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        JOIN res_partner rp ON rp.id = so.partner_id
        WHERE so.state != 'cancel'
        GROUP BY rp.name
        ORDER BY ca_ht DESC
    """)
    rows = []
    for r in c.fetchall():
        d = {col: flt(v) for col, v in dict(r).items()}
        d["pct_ca"]      = round(d["ca_ht"] / total * 100, 2)
        d["marge_brute"] = round(d["ca_ht"] * 0.1691, 2)
        d["taux_marge"]  = 16.91
        rows.append(d)

    c.close(); conn.close()
    return rows


def get_categories():
    """CA par catégorie — barres horizontales Page 1 et Page 3"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    c.execute("SELECT ROUND(SUM(sol.price_subtotal)::numeric,2) t FROM sale_order so JOIN sale_order_line sol ON sol.order_id=so.id WHERE so.state!='cancel'")
    total = flt(c.fetchone()["t"]) or 1

    c.execute("""
        SELECT
            CASE
                WHEN pc.name::text LIKE '%fr_FR%' THEN (pc.name::jsonb) ->> 'fr_FR'
                WHEN pc.name::text LIKE '%en_US%' THEN (pc.name::jsonb) ->> 'en_US'
                ELSE pc.name::text
            END                                                                 AS categorie,
            ROUND(SUM(sol.price_subtotal)::numeric, 2)                         AS ca_ht,
            SUM(sol.product_uom_qty)                                            AS qte_vendue
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        JOIN product_product pp  ON pp.id = sol.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        JOIN product_category pc ON pc.id = pt.categ_id
        WHERE so.state != 'cancel'
        GROUP BY pc.name
        ORDER BY ca_ht DESC
    """)
    rows = []
    for r in c.fetchall():
        d = {col: flt(v) for col, v in dict(r).items()}
        d["pct_ca"] = round(d["ca_ht"] / total * 100, 2)
        rows.append(d)

    c.close(); conn.close()
    return rows


# ── PAGE 2 : Analyse Commerciale ─────────────────────────

def get_statuts():
    """Répartition commandes par statut — anneau Page 2"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("SELECT state, COUNT(*) nb FROM sale_order GROUP BY state ORDER BY nb DESC")
    rows   = [dict(r) for r in c.fetchall()]
    total  = sum(r["nb"] for r in rows)
    result = [{"state": r["state"], "nb": r["nb"],
               "pct": round(r["nb"] / total * 100, 1) if total else 0}
              for r in rows]
    c.close(); conn.close()
    return result


# ── DONNÉES SUPPLÉMENTAIRES (hors dashboard) ──────────────

def get_historique_commandes():
    """Toutes les commandes avec détails — pour questions hors dashboard"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            so.name                                         AS numero_commande,
            TO_CHAR(so.date_order, 'YYYY-MM-DD')            AS date_commande,
            rp.name                                         AS client,
            so.state                                        AS statut,
            ROUND(so.amount_untaxed::numeric, 2)            AS montant_ht,
            ROUND(so.amount_total::numeric, 2)              AS montant_ttc,
            COUNT(sol.id)                                   AS nb_lignes,
            SUM(sol.product_uom_qty)                        AS qte_totale
        FROM sale_order so
        JOIN res_partner rp      ON rp.id = so.partner_id
        JOIN sale_order_line sol ON sol.order_id = so.id
        GROUP BY so.id, so.name, so.date_order, rp.name,
                 so.state, so.amount_untaxed, so.amount_total
        ORDER BY so.date_order DESC
        LIMIT 50
    """)
    result = [{col: flt(v) for col, v in dict(r).items()} for r in c.fetchall()]
    c.close(); conn.close()
    return result


def get_tous_produits():
    """Catalogue complet des produits avec prix et catégorie"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            CASE
                WHEN pt.name::text LIKE '%fr_FR%' THEN (pt.name::jsonb) ->> 'fr_FR'
                WHEN pt.name::text LIKE '%en_US%' THEN (pt.name::jsonb) ->> 'en_US'
                ELSE pt.name::text
            END                                        AS produit,
            CASE
                WHEN pc.name::text LIKE '%fr_FR%' THEN (pc.name::jsonb) ->> 'fr_FR'
                WHEN pc.name::text LIKE '%en_US%' THEN (pc.name::jsonb) ->> 'en_US'
                ELSE pc.name::text
            END                                        AS categorie,
            ROUND(pt.list_price::numeric, 2)           AS prix_vente,
            pt.active                                  AS actif,
            pt.type                                    AS type_produit
        FROM product_template pt
        JOIN product_category pc ON pc.id = pt.categ_id
        WHERE pt.active = true
        ORDER BY pc.name, pt.list_price DESC
    """)
    result = []
    for r in c.fetchall():
        d = dict(r)
        d["prix_vente"] = flt(d["prix_vente"])
        result.append(d)
    c.close(); conn.close()
    return result


def get_clients_details():
    """Informations détaillées sur tous les clients"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            rp.name                                         AS client,
            rp.email                                        AS email,
            rp.phone                                        AS telephone,
            rp.city                                         AS ville,
            rp.customer_rank                                AS rang_client,
            COUNT(DISTINCT so.id)                           AS nb_commandes_total,
            ROUND(SUM(sol.price_subtotal)::numeric, 2)      AS ca_total,
            TO_CHAR(MIN(so.date_order), 'YYYY-MM-DD')       AS premiere_commande,
            TO_CHAR(MAX(so.date_order), 'YYYY-MM-DD')       AS derniere_commande
        FROM res_partner rp
        LEFT JOIN sale_order so      ON so.partner_id = rp.id
                                    AND so.state != 'cancel'
        LEFT JOIN sale_order_line sol ON sol.order_id = so.id
        WHERE rp.customer_rank > 0
        GROUP BY rp.id, rp.name, rp.email, rp.phone,
                 rp.city, rp.customer_rank
        ORDER BY ca_total DESC NULLS LAST
    """)
    result = []
    for r in c.fetchall():
        d = dict(r)
        d["ca_total"] = flt(d["ca_total"] or 0)
        result.append(d)
    c.close(); conn.close()
    return result


def get_ca_par_produit_et_client():
    """CA croisé produit × client — pour analyses détaillées"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            rp.name                                        AS client,
            CASE
                WHEN pt.name::text LIKE '%fr_FR%' THEN (pt.name::jsonb) ->> 'fr_FR'
                WHEN pt.name::text LIKE '%en_US%' THEN (pt.name::jsonb) ->> 'en_US'
                ELSE pt.name::text
            END                                            AS produit,
            SUM(sol.product_uom_qty)                       AS qte_vendue,
            ROUND(SUM(sol.price_subtotal)::numeric, 2)     AS ca_ht
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        JOIN res_partner rp      ON rp.id = so.partner_id
        JOIN product_product pp  ON pp.id = sol.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE so.state != 'cancel'
        GROUP BY rp.name, pt.name
        ORDER BY ca_ht DESC
        LIMIT 30
    """)
    result = [{col: flt(v) for col, v in dict(r).items()} for r in c.fetchall()]
    c.close(); conn.close()
    return result


def get_tendances_hebdo():
    """Ventes par semaine — pour analyser les tendances"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            TO_CHAR(DATE_TRUNC('week', so.date_order), 'YYYY-MM-DD') AS semaine,
            COUNT(DISTINCT so.id)                                      AS nb_commandes,
            ROUND(SUM(sol.price_subtotal)::numeric, 2)                AS ca_ht,
            SUM(sol.product_uom_qty)                                   AS qte_vendue
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        WHERE so.state != 'cancel'
        GROUP BY DATE_TRUNC('week', so.date_order)
        ORDER BY semaine
    """)
    result = [{col: flt(v) for col, v in dict(r).items()} for r in c.fetchall()]
    c.close(); conn.close()
    return result


def get_devis_non_convertis():
    """Devis non convertis en commandes — opportunités commerciales"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            so.name                                         AS numero_devis,
            TO_CHAR(so.date_order, 'YYYY-MM-DD')            AS date_devis,
            rp.name                                         AS client,
            so.state                                        AS statut,
            ROUND(so.amount_untaxed::numeric, 2)            AS montant_ht,
            (CURRENT_DATE - so.date_order::date)            AS jours_en_attente
        FROM sale_order so
        JOIN res_partner rp ON rp.id = so.partner_id
        WHERE so.state IN ('draft', 'sent')
        ORDER BY so.amount_untaxed DESC
    """)
    result = []
    for r in c.fetchall():
        d = dict(r)
        d["montant_ht"]       = flt(d["montant_ht"])
        d["jours_en_attente"] = int(d["jours_en_attente"]) if d["jours_en_attente"] else 0
        result.append(d)
    c.close(); conn.close()
    return result


def get_qte_par_mois():
    """Quantité vendue par mois — anneau Page 2"""
    evo = get_evolution_ca()
    total_qte = sum(r["qte_vendue"] for r in evo) or 1
    return [
        {
            "mois"       : r["mois_nom"],
            "annee_mois" : r["annee_mois"],
            "qte_vendue" : r["qte_vendue"],
            "pct"        : round(r["qte_vendue"] / total_qte * 100, 2),
            "ca_ht"      : r["ca_ht"],
            "nb_commandes": r["nb_commandes"]
        }
        for r in evo
    ]


# ── PAGE 3 : Analyse Produits ─────────────────────────────

def get_kpis_produits():
    """
    KPIs Page 3 :
    Prix Moyen=478.63 | Qté=836 | Distincts=38 | Top Produits Qté=175 | Non Vendus=53
    """
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # KPIs de base
    c.execute("""
        SELECT
            COUNT(DISTINCT sol.product_id)                  AS nb_distincts,
            SUM(sol.product_uom_qty)                        AS qte_totale,
            ROUND(AVG(sol.price_unit)::numeric, 2)          AS prix_moyen
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        WHERE so.state != 'cancel'
    """)
    result = {col: flt(v) for col, v in dict(c.fetchone()).items()}

    # Quantité Top Produits = qté du produit le plus vendu
    c.execute("""
        SELECT SUM(sol.product_uom_qty) AS qte_top
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        JOIN product_product pp  ON pp.id = sol.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE so.state != 'cancel'
        GROUP BY pt.name
        ORDER BY qte_top DESC
        LIMIT 1
    """)
    top = c.fetchone()
    result["qte_top_produit"] = flt(top["qte_top"]) if top else 0

    # NB Produits Non Vendues = produits dans product_template sans ventes
    c.execute("""
        SELECT COUNT(*) AS nb_non_vendus
        FROM product_template pt
        WHERE pt.active = true
          AND pt.id NOT IN (
              SELECT DISTINCT pp2.product_tmpl_id
              FROM sale_order_line sol2
              JOIN product_product pp2 ON pp2.id = sol2.product_id
              JOIN sale_order so2 ON so2.id = sol2.order_id
              WHERE so2.state != 'cancel'
          )
    """)
    nv = c.fetchone()
    result["nb_non_vendus"] = flt(nv["nb_non_vendus"]) if nv else 0

    c.close(); conn.close()
    return result


def get_top10_ca():
    """Top 10 produits par CA — Page 3"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            CASE
                WHEN pt.name::text LIKE '%fr_FR%' THEN (pt.name::jsonb) ->> 'fr_FR'
                WHEN pt.name::text LIKE '%en_US%' THEN (pt.name::jsonb) ->> 'en_US'
                ELSE pt.name::text
            END                                                                 AS produit,
            ROUND(SUM(sol.price_subtotal)::numeric, 2)                         AS ca_ht,
            SUM(sol.product_uom_qty)                                            AS qte_vendue,
            ROUND(AVG(sol.price_unit)::numeric, 2)                             AS prix_moyen,
            ROUND(SUM(sol.price_subtotal)::numeric
                  / NULLIF(SUM(sol.product_uom_qty), 0), 2)                    AS panier_moyen
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        JOIN product_product pp  ON pp.id = sol.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE so.state != 'cancel'
        GROUP BY pt.name
        ORDER BY ca_ht DESC
        LIMIT 10
    """)
    result = [{col: flt(v) for col, v in dict(r).items()} for r in c.fetchall()]
    c.close(); conn.close()
    return result


def get_top5_qte():
    """Top 5 produits par quantité — camembert Page 3"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            CASE
                WHEN pt.name::text LIKE '%fr_FR%' THEN (pt.name::jsonb) ->> 'fr_FR'
                WHEN pt.name::text LIKE '%en_US%' THEN (pt.name::jsonb) ->> 'en_US'
                ELSE pt.name::text
            END                                                                 AS produit,
            SUM(sol.product_uom_qty)                                            AS qte_vendue,
            ROUND(SUM(sol.price_subtotal)::numeric, 2)                         AS ca_ht
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        JOIN product_product pp  ON pp.id = sol.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE so.state != 'cancel'
        GROUP BY pt.name
        ORDER BY qte_vendue DESC
        LIMIT 5
    """)
    conn2 = get_conn()
    c2 = conn2.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c2.execute("SELECT SUM(sol.product_uom_qty) t FROM sale_order so JOIN sale_order_line sol ON sol.order_id=so.id WHERE so.state!='cancel'")
    total = flt(c2.fetchone()["t"]) or 1
    c2.close(); conn2.close()

    rows = []
    for r in c.fetchall():
        d = {col: flt(v) for col, v in dict(r).items()}
        d["pct"] = round(d["qte_vendue"] / total * 100, 2)
        rows.append(d)

    c.close(); conn.close()
    return rows


def get_top10_panier():
    """Top 10 produits par panier moyen — graphique Page 3"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            CASE
                WHEN pt.name::text LIKE '%fr_FR%' THEN (pt.name::jsonb) ->> 'fr_FR'
                WHEN pt.name::text LIKE '%en_US%' THEN (pt.name::jsonb) ->> 'en_US'
                ELSE pt.name::text
            END                                                                 AS produit,
            ROUND(SUM(sol.price_subtotal)::numeric
                  / NULLIF(SUM(sol.product_uom_qty), 0), 2)                    AS panier_moyen,
            SUM(sol.product_uom_qty)                                            AS qte_vendue,
            ROUND(SUM(sol.price_subtotal)::numeric, 2)                         AS ca_ht
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        JOIN product_product pp  ON pp.id = sol.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE so.state != 'cancel'
        GROUP BY pt.name
        ORDER BY panier_moyen DESC
        LIMIT 10
    """)
    result = [{col: flt(v) for col, v in dict(r).items()} for r in c.fetchall()]
    c.close(); conn.close()
    return result


def get_detail_produits():
    """Détail ventes par produit — tableau Page 3"""
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT
            CASE
                WHEN pt.name::text LIKE '%fr_FR%' THEN (pt.name::jsonb) ->> 'fr_FR'
                WHEN pt.name::text LIKE '%en_US%' THEN (pt.name::jsonb) ->> 'en_US'
                ELSE pt.name::text
            END                                                                 AS produit,
            SUM(sol.product_uom_qty)                                            AS qte_vendue,
            ROUND(SUM(sol.price_total)::numeric, 2)                            AS ca_total,
            ROUND(SUM(sol.price_subtotal) * 0.1691, 2)                         AS marge_brute
        FROM sale_order so
        JOIN sale_order_line sol ON sol.order_id = so.id
        JOIN product_product pp  ON pp.id = sol.product_id
        JOIN product_template pt ON pt.id = pp.product_tmpl_id
        WHERE so.state != 'cancel'
        GROUP BY pt.name
        ORDER BY qte_vendue DESC
    """)
    result = [{col: flt(v) for col, v in dict(r).items()} for r in c.fetchall()]
    c.close(); conn.close()
    return result


# ── Fonction principale ───────────────────────────────────

def get_all_data():
    """
    Récupère TOUTES les données :
    - Données du rapport Power BI 'stage bi' (3 pages)
    - Données supplémentaires pour questions hors dashboard
    """
    kpis = get_kpis()
    return {
        # ── Rapport Power BI — Page 1 ─────────────────────
        "kpis"              : kpis,
        "evolution_ca"      : get_evolution_ca(),
        "clients"           : get_clients(),
        "categories"        : get_categories(),

        # ── Rapport Power BI — Page 2 ─────────────────────
        "statuts"           : get_statuts(),
        "qte_par_mois"      : get_qte_par_mois(),

        # ── Rapport Power BI — Page 3 ─────────────────────
        "kpis_prod"         : get_kpis_produits(),
        "top10_ca"          : get_top10_ca(),
        "top5_qte"          : get_top5_qte(),
        "top10_panier"      : get_top10_panier(),
        "detail_produits"   : get_detail_produits(),

        # ── Données supplémentaires (hors dashboard) ──────
        "historique"        : get_historique_commandes(),
        "tous_produits"     : get_tous_produits(),
        "clients_details"   : get_clients_details(),
        "croise_produit_client": get_ca_par_produit_et_client(),
        "tendances_hebdo"   : get_tendances_hebdo(),
        "devis_non_convertis": get_devis_non_convertis(),
    }
