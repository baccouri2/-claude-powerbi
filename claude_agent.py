"""
claude_agent.py
Agent Claude via CometAPI — données directes Power BI Desktop
"""

import anthropic, json
from config import CLAUDE_API_KEY, CLAUDE_BASE_URL, CLAUDE_MODEL

# Client Claude via CometAPI
_client = anthropic.Anthropic(
    base_url=CLAUDE_BASE_URL,
    api_key=CLAUDE_API_KEY
)


def build_system_prompt(data: dict) -> str:
    """Prompt système avec toutes les données Power BI"""
    k  = data.get("kpis", {})
    kp = data.get("kpis_prod", {})

    return f"""Tu es un expert analyste BI spécialisé dans Odoo.
Tu analyses les données EN TEMPS RÉEL du rapport Power BI "stage bi".
Réponds TOUJOURS en français, de manière professionnelle et précise.

RAPPORT POWER BI "stage bi" — MODULE VENTE ODOO
================================================

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

Quantité vendue par client (visuel Page 1) :
{json.dumps(data.get("qte_par_client", []), ensure_ascii=False, indent=2)}

Quantité vendue par client et par mois :
{json.dumps(data.get("qte_client_mois", []), ensure_ascii=False, indent=2)}

■ PAGE 2 — ANALYSE COMMERCIALE
Statuts des commandes :
{json.dumps(data.get("statuts", []), ensure_ascii=False, indent=2)}

■ PAGE 3 — ANALYSE PRODUITS
  Prix Moyen Produits    : {kp.get("prix_moyen",0):,.2f} DT
  Nb Produits Distincts  : {int(kp.get("nb_distincts",0))}
  Qté Totale Vendue      : {int(kp.get("qte_totale",0))}
  Quantité Top Produits  : {int(kp.get("qte_top_produit",0))}
  NB Produits Non Vendus : {int(kp.get("nb_non_vendus",0))}

Top 10 produits par CA :
{json.dumps(data.get("top10_ca", []), ensure_ascii=False, indent=2)}

Top 5 produits par quantité :
{json.dumps(data.get("top5_qte", []), ensure_ascii=False, indent=2)}

Top 10 produits par panier moyen :
{json.dumps(data.get("top10_panier", []), ensure_ascii=False, indent=2)}

================================================
RÈGLES : Cite les chiffres exacts. Réponds en français."""


def chat(question: str, historique: list, data: dict) -> dict:
    """Conversation Claude avec données Power BI"""
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
