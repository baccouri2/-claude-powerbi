# Claude AI — Rapport Power BI "stage bi"

Synchronisation automatique des données du rapport Power BI avec Claude AI.

## Lancement

```bash
python app.py
```

Puis ouvrir : **http://localhost:5000**

## Dans Power BI

```
Insérer → Boutons → Vide
→ Action → URL Web → http://localhost:5000
```

## Structure

```
claude_powerbi/
├── app.py           # Serveur Flask
├── config.py        # Configuration DB + Claude
├── database.py      # Requêtes SQL synchronisées avec Power BI
├── claude_agent.py  # Agent Claude via CometAPI
├── requirements.txt
├── templates/
│   └── index.html
└── static/
    ├── css/style.css
    └── js/app.js
```
