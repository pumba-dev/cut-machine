@echo off
REM Publica o proximo short pendente da conta politica/Politica em Bits (Agendador de Tarefas do Windows).
cd /d "C:\Users\eduar\github\social-accounts-agent"
"C:\Program Files\Python313\python.exe" scripts\publish_next.py --format short --account politica >> logs\publish_short.log 2>&1
