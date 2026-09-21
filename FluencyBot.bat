@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Todavía no está instalado: primero haz doble clic en instalar.bat
    echo.
    pause
    exit /b 1
)

rem -u: sin buffer, para que la salida y el log se vean al momento. La
rem primera vez, si falta el archivo .env, el propio bot pide los datos.
"venv\Scripts\python.exe" -u bot.py

echo.
pause
