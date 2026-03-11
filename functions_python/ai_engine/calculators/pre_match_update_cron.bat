@echo off
REM Cron job — Pre-Match Update (ogni 15 minuti, 10:00-23:00)
REM Chiamato da Windows Task Scheduler

cd /d "C:\Progetti\simulatore-calcio-backend\functions_python\ai_engine\calculators"

REM Log con timestamp
echo. >> "C:\Progetti\simulatore-calcio-backend\log\pre_match_update.log"
echo ===== %date% %time% ===== >> "C:\Progetti\simulatore-calcio-backend\log\pre_match_update.log"

python pre_match_update.py >> "C:\Progetti\simulatore-calcio-backend\log\pre_match_update.log" 2>&1
