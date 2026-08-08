@echo off
REM ============================================================
REM run_sync.bat
REM Lance la synchronisation Sage 100 -> data/products.json -> GitHub
REM A planifier via le Planificateur de taches Windows.
REM ============================================================

cd /d "%~dp0"

echo [%date% %time%] Debut synchronisation stock Sage 100 >> sync_stock.log

python sync_stock.py >> sync_stock.log 2>&1

echo [%date% %time%] Fin synchronisation (code retour %ERRORLEVEL%) >> sync_stock.log

exit /b %ERRORLEVEL%
