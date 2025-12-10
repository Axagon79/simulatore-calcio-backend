@echo off
set "CARTELLA_PROGETTO=C:\Progetti\simulatore-calcio-backend"

set "RPT_TOTAL=total_simulation_report.html"
set "RPT_SINGLE=simulation_report.html"

echo.
echo ================================
echo 📊 APERTURA REPORT SIMULAZIONI
echo ================================
echo.
echo  [1] TOTAL SIMULATION        (%RPT_TOTAL%)
echo  [2] Ultima simulazione singola/giornata  (%RPT_SINGLE%)
echo  [3] Annulla
echo.
set /p SCELTA="Scelta: "

if "%SCELTA%"=="1" goto OPEN_TOTAL
if "%SCELTA%"=="2" goto OPEN_SINGLE
goto END

:OPEN_TOTAL
if exist "%CARTELLA_PROGETTO%\%RPT_TOTAL%" (
    echo.
    echo ➜ Apro %RPT_TOTAL% ...
    start "" "%CARTELLA_PROGETTO%\%RPT_TOTAL%"
) else (
    echo.
    echo ❌ TOTAL SIMULATION non trovata:
    echo    %CARTELLA_PROGETTO%\%RPT_TOTAL%
    pause
)
goto END

:OPEN_SINGLE
if exist "%CARTELLA_PROGETTO%\%RPT_SINGLE%" (
    echo.
    echo ➜ Apro %RPT_SINGLE% ...
    start "" "%CARTELLA_PROGETTO%\%RPT_SINGLE%"
) else (
    echo.
    echo ❌ Report singolo non trovato:
    echo    %CARTELLA_PROGETTO%\%RPT_SINGLE%
    pause
)
goto END

:END
