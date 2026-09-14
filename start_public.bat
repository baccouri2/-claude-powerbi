@echo off
title Claude AI — Serveur Public
cd /d "C:\Users\ranin baccouri\Desktop\claude_powerbi"

echo Demarrage du serveur Claude AI...
start /min "" python -X utf8 app.py

echo Attente demarrage serveur (5 secondes)...
timeout /t 5 /nobreak >nul

echo Demarrage tunnel ngrok...
start "" ngrok http 5000

echo.
echo Copie l'URL https://xxxx.ngrok.io
echo et donne-la a ton encadrante !
echo.
pause
