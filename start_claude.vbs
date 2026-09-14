' Démarre Claude AI en arrière-plan (sans fenêtre visible)
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d ""C:\Users\ranin baccouri\Desktop\claude_powerbi"" && python -X utf8 app.py", 0, False
