@echo off
cd /d "C:\Progetti\simulatore-calcio-backend"
call .venv\Scripts\activate
python ai_engine\engine\tuning_server.py
pause
