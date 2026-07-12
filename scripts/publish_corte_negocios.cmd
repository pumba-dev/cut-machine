@echo off
REM Publica o proximo corte pendente da conta negocios/Economia de Bits (Agendador de Tarefas do Windows).
cd /d "C:\Users\eduar\github\social-accounts-agent"
"C:\Program Files\Python313\python.exe" scripts\publish_next.py --format corte --account negocios >> logs\publish_corte_negocios.log 2>&1
