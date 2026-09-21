@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==================================================
echo   FluencyBot - instalación (solo la primera vez)
echo ==================================================
echo.

rem --- 1. Buscar Python 3.10 o superior -------------------------------
rem Se prueba ejecutándolo de verdad: en muchos equipos "python" es un
rem acceso directo de la Microsoft Store que abre la tienda en vez de
rem ejecutar nada, y solo con buscarlo en el PATH parecería que existe.
set "PY="
call :probar_python py -3
if not defined PY call :probar_python python
if not defined PY call :probar_python "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

if not defined PY (
    echo No se encontró Python 3.10 o superior.
    echo.
    choice /c SN /m "¿Instalar Python 3.12 ahora con winget"
    if errorlevel 2 goto :sin_python
    winget install -e --id Python.Python.3.12 --scope user
    rem Recién instalado todavía no está en el PATH de esta ventana:
    rem se busca en la carpeta donde lo deja winget.
    call :probar_python "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY goto :sin_python
echo Python encontrado: %PY%
echo.

rem --- 2. Entorno propio del bot ---------------------------------------
rem Todo se instala dentro de la carpeta "venv", sin tocar el resto del
rem equipo. Para desinstalar basta con borrar la carpeta del bot.
if not exist "venv\Scripts\python.exe" (
    echo Creando el entorno de Python del bot...
    %PY% -m venv venv || goto :error
)

echo Instalando dependencias...
"venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || goto :error

echo Descargando el navegador que usa el bot...
"venv\Scripts\python.exe" -m playwright install chromium --no-shell || goto :error

echo.
echo ==================================================
echo   Listo. Para usar el bot: doble clic en FluencyBot.bat
echo ==================================================
echo.
pause
exit /b 0


:probar_python
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%*"
exit /b


:sin_python
echo.
echo Hace falta Python 3.10 o superior. Descárgalo de https://www.python.org/downloads/
echo y al instalarlo marca la casilla "Add python.exe to PATH".
echo Después vuelve a abrir este archivo.
echo.
pause
exit /b 1


:error
echo.
echo Algo falló en el paso de arriba. Revisa el mensaje y vuelve a intentarlo.
echo.
pause
exit /b 1
