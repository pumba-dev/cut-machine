@echo off
REM Publica o proximo corte pendente (chamado pelo Agendador de Tarefas do Windows).
cd /d "C:\Users\eduar\github\social-accounts-agent"
"C:\Program Files\Python313\python.exe" scripts\publish_next.py --format corte >> logs\publish_corte.log 2>&1
