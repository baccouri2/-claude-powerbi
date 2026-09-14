import os

# ── Connexion PostgreSQL Odoo ─────────────────────────────
# Lit depuis les variables d'environnement (Render)
# ou utilise les valeurs locales par défaut
DB_CONFIG = {
    "host"    : os.environ.get("DB_HOST",     "63.250.55.89"),
    "port"    : int(os.environ.get("DB_PORT", "6432")),
    "database": os.environ.get("DB_NAME",     "compta_test_27_07"),
    "user"    : os.environ.get("DB_USER",     "compta_user"),
    "password": os.environ.get("DB_PASSWORD", "yuiikcçBLJDFgil")
}

# ── Claude via CometAPI ───────────────────────────────────
CLAUDE_API_KEY  = os.environ.get("CLAUDE_API_KEY",
                  "jJpe7kVl1djoLlPxJdprdRiBdCc979AAcrOflFZP47rpWsjl")
CLAUDE_BASE_URL = "https://api.cometapi.com"
CLAUDE_MODEL    = "claude-sonnet-5"

# ── Power BI Desktop (local uniquement) ──────────────────
PBI_PORT   = int(os.environ.get("PBI_PORT", "51468"))
PBI_SERVER = f"localhost:{PBI_PORT}"

# ── Flask ─────────────────────────────────────────────────
PORT  = int(os.environ.get("PORT", "5000"))
DEBUG = False
