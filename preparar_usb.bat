@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Preparar la USB de AulaCoach
echo.
echo   Prepara esta carpeta para instalar AulaCoach en una escuela SIN internet.
echo   Use una computadora CON internet que tenga Python y Ollama instalados.
echo   Se descargan unos 3.5 GB: puede tardar.
echo.
python -c "import sys" >nul 2>nul
if errorlevel 1 (
  echo   Falta Python en esta computadora. Instalelo desde python.org y vuelva a intentar.
  goto :error
)
if not exist "instalador" mkdir "instalador"

rem --- Instaladores de Python y Ollama para la escuela ---
set "PYVER=3.12.10"
if exist "instalador\python-%PYVER%-amd64.exe" goto :ollama
echo   Descargando el instalador de Python %PYVER%...
curl -L --fail -o "instalador\python-%PYVER%-amd64.exe" "https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe"
if errorlevel 1 (
  del "instalador\python-%PYVER%-amd64.exe" >nul 2>nul
  echo   No se pudo descargar. Bajelo a mano de python.org y guardelo en la carpeta instalador.
)

:ollama
if exist "instalador\OllamaSetup.exe" goto :paquetes
echo   Descargando el instalador de Ollama...
curl -L --fail -o "instalador\OllamaSetup.exe" "https://ollama.com/download/OllamaSetup.exe"
if errorlevel 1 (
  del "instalador\OllamaSetup.exe" >nul 2>nul
  echo   No se pudo descargar. Bajelo a mano de ollama.com y guardelo en la carpeta instalador como OllamaSetup.exe
)

:paquetes
rem --- Paquetes de Python y modelo de IA ---
python usb.py preparar --sistema windows --python 3.12
if errorlevel 1 goto :error
echo.
echo   Listo. Copie la carpeta completa de AulaCoach a la USB.
echo   En la escuela: doble clic en instalar_sin_internet.bat
echo.
pause
exit /b 0

:error
echo.
echo   No se pudo terminar. Revise el mensaje de arriba.
pause
exit /b 1
