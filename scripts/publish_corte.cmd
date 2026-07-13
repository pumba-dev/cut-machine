@echo off
REM Publica o proximo corte pendente da conta politica/Politica em Bits (Agendador de Tarefas do Windows).
cd /d "C:\Users\eduar\github\social-accounts-agent"
"C:\Program Files\Python313\python.exe" scripts\publish_next.py --format corte --account politica >> logs\publish_corte.log 2>&1
