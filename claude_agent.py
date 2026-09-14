"""
claude_agent.py
Agent Claude via CometAPI
Données dashboard Power BI + données supplémentaires Odoo
"""

import anthropic, json
from config import CLAUDE_API_KEY, CLAUDE_BASE_URL, CLAUDE_MODEL

_client = anthropic.Anthropic(
    base_url=CLAUDE_BASE_URL,
    api_key=CLAUDE_API_KEY
)


def build_system_prompt(data: dict) -> str:
    """Prompt avec données dashboard + données supplémentaires"""
    k  = data.get("kpis", {})
    kp = data.get("kpis_prod", {})

    return f"""Tu es un expert analyste BI spécialisé dans Odoo.
Tu analyses les données EN TEMPS RÉEL du rapport Power BI "stage bi".
Réponds TOUJOURS en français, de manière professionnelle et précise.
Tu peux répondre à TOUTES les questions sur les ventes, clients,
produits, tendances, recommandations — même hors dashboard.

════════════════════════════════════════════════
RAPPORT POWER BI "stage bi" — 3 PAGES
════════════════════════════════════════════════

■ PAGE 1 — VUE GÉNÉRALE
  CA Total HT     : {k.get("ca_ht",0):,.2f} DT
  Marge Brute     : {k.get("marge_brute",0):,.2f} DT
  Taux de Marge   : {k.get("taux_marge",0):.2f}%
  Taux Conversion : {k.get("taux_conversion",0):.2f}%
  Nb Commandes    : {int(k.get("nb_commandes",0))}
  Nb Clients      : {int(k.get("nb_clients",0))}
  Panier Moyen    : {k.get("panier_moyen",0):,.2f} DT
  Qté Vendue      : {int(k.get("qte_vendue",0))}

Évolution CA par mois :
{json.dumps(data.get("evolution_ca", []), ensure_ascii=False, indent=2)}

CA par client :
{json.dumps(data.get("clients", []), ensure_ascii=False, indent=2)}

CA par catégorie :
{json.dumps(data.get("categories", []), ensure_ascii=False, indent=2)}

■ PAGE 2 — ANALYSE COMMERCIALE
Statuts commandes :
{json.dumps(data.get("statuts", []), ensure_ascii=False, indent=2)}

Quantité par mois :
{json.dumps(data.get("qte_par_mois", []), ensure_ascii=False, indent=2)}

■ PAGE 3 — ANALYSE PRODUITS
  Prix Moyen     : {kp.get("prix_moyen",0):,.2f} DT
  Nb Distincts   : {int(kp.get("nb_distincts",0))}
  Qté Top Produit: {int(kp.get("qte_top_produit",0))}
  Non Vendus     : {int(kp.get("nb_non_vendus",0))}

Top 10 produits par CA :
{json.dumps(data.get("top10_ca", []), ensure_ascii=False, indent=2)}

Top 5 produits par quantité :
{json.dumps(data.get("top5_qte", []), ensure_ascii=False, indent=2)}

Top 10 produits par panier moyen :
{json.dumps(data.get("top10_panier", []), ensure_ascii=False, indent=2)}

Détail ventes par produit :
{json.dumps(data.get("detail_produits", []), ensure_ascii=False, indent=2)}

════════════════════════════════════════════════
DONNÉES SUPPLÉMENTAIRES ODOO (hors dashboard)
════════════════════════════════════════════════

Historique des 50 dernières commandes :
{json.dumps(data.get("historique", []), ensure_ascii=False, indent=2)}

Catalogue complet des produits (prix, catégorie, type) :
{json.dumps(data.get("tous_produits", []), ensure_ascii=False, indent=2)}

Détails clients (email, ville, historique complet) :
{json.dumps(data.get("clients_details", []), ensure_ascii=False, indent=2)}

CA croisé Produit × Client (Top 30) :
{json.dumps(data.get("croise_produit_client", []), ensure_ascii=False, indent=2)}

Tendances par semaine :
{json.dumps(data.get("tendances_hebdo", []), ensure_ascii=False, indent=2)}

Devis non convertis (opportunités commerciales) :
{json.dumps(data.get("devis_non_convertis", []), ensure_ascii=False, indent=2)}

════════════════════════════════════════════════
RÈGLES :
- Utilise ces données pour répondre à TOUTES les questions
- Cite les chiffres exacts
- Réponds en français
- Si une question dépasse les données disponibles,
  dis-le clairement et propose une analyse basée sur
  les données existantes
════════════════════════════════════════════════"""


def chat(question: str, historique: list, data: dict) -> dict:
    """Conversation Claude avec toutes les données"""
    system   = build_system_prompt(data)
    messages = []
    for msg in historique:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": question})

    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=system,
            messages=messages
        )
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        return {"success": True, "response": text}

    except Exception as e:
        err = str(e)
        if "429" in err:
            return {"success": False,
                    "response": "⚠️ Limite atteinte. Réessayez dans quelques secondes."}
        return {"success": False, "response": f"❌ Erreur Claude : {err}"}
