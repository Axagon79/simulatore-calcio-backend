@echo off
:: --- CONFIGURAZIONE ---
set "CARTELLA_PROGETTO=C:\Progetti\simulatore-calcio-backend\"
set "NOME_REPORT=total_simulation_report.html"

:: --- ESECUZIONE ---
if exist "%CARTELLA_PROGETTO%\%NOME_REPORT%" (
    echo Apertura del report in corso...
    start "" "%CARTELLA_PROGETTO%\%NOME_REPORT%"
) else (
    echo.
    echo ❌ ERRORE: Il report non è stato trovato!
    echo Cercavo: %CARTELLA_PROGETTO%\%NOME_REPORT%
    echo.
    pause
)
