"""
claude_agent.py
Agent Claude via CometAPI
Données dashboard Power BI + données supplémentaires Odoo
"""

import anthropic
from config import CLAUDE_API_KEY, CLAUDE_BASE_URL, CLAUDE_MODEL
from datetime import date, datetime
from decimal import Decimal
import json

_client = anthropic.Anthropic(
    base_url=CLAUDE_BASE_URL,
    api_key=CLAUDE_API_KEY
)


# ── Sérialisation JSON sécurisée ──────────────────────────
class SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


def safe_json(data) -> str:
    """Convertit n'importe quelle donnée en JSON string sécurisée"""
    return json.dumps(data, cls=SafeEncoder, ensure_ascii=False, indent=2)


def build_system_prompt(data: dict) -> str:
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
  Période         : {k.get("date_debut","")} → {k.get("date_fin","")}

Évolution CA par mois :
{safe_json(data.get("evolution_ca", []))}

CA par client :
{safe_json(data.get("clients", []))}

CA par catégorie :
{safe_json(data.get("categories", []))}

■ PAGE 2 — ANALYSE COMMERCIALE
Statuts commandes :
{safe_json(data.get("statuts", []))}

Quantité par mois :
{safe_json(data.get("qte_par_mois", []))}

■ PAGE 3 — ANALYSE PRODUITS
  Prix Moyen     : {kp.get("prix_moyen",0):,.2f} DT
  Nb Distincts   : {int(kp.get("nb_distincts",0))}
  Qté Top Produit: {int(kp.get("qte_top_produit",0))}
  Non Vendus     : {int(kp.get("nb_non_vendus",0))}

Top 10 produits par CA :
{safe_json(data.get("top10_ca", []))}

Top 5 produits par quantité :
{safe_json(data.get("top5_qte", []))}

Top 10 produits par panier moyen :
{safe_json(data.get("top10_panier", []))}

Détail ventes par produit :
{safe_json(data.get("detail_produits", []))}

════════════════════════════════════════════════
DONNÉES SUPPLÉMENTAIRES ODOO (hors dashboard)
════════════════════════════════════════════════

Historique des 50 dernières commandes :
{safe_json(data.get("historique", []))}

Catalogue complet des produits :
{safe_json(data.get("tous_produits", []))}

Détails clients (email, ville, historique) :
{safe_json(data.get("clients_details", []))}

CA croisé Produit × Client (Top 30) :
{safe_json(data.get("croise_produit_client", []))}

Tendances par semaine :
{safe_json(data.get("tendances_hebdo", []))}

Devis non convertis (opportunités) :
{safe_json(data.get("devis_non_convertis", []))}

════════════════════════════════════════════════
RÈGLES :
- Utilise ces données pour répondre à TOUTES les questions
- Cite les chiffres exacts
- Réponds en français
════════════════════════════════════════════════"""


def chat(question: str, historique: list, data: dict) -> dict:
    """Conversation Claude avec toutes les données"""
    try:
        system   = build_system_prompt(data)
        messages = []

        # Garder seulement les 6 derniers échanges (3 Q + 3 R)
        # pour éviter de dépasser la limite de tokens
        recent = historique[-6:] if len(historique) > 6 else historique
        for msg in recent:
            # Tronquer les réponses longues dans l'historique
            content = msg["content"]
            if msg["role"] == "assistant" and len(content) > 1000:
                content = content[:1000] + "...[suite tronquée]"
            messages.append({"role": msg["role"], "content": content})

        messages.append({"role": "user", "content": question})

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
        if "max_tokens" in err.lower() or "context" in err.lower() or "length" in err.lower():
            return {"success": False,
                    "response": "⚠️ Conversation trop longue. Cliquez sur 'Nouvelle conversation' pour continuer."}
        return {"success": False, "response": f"❌ Erreur Claude : {err}"}
