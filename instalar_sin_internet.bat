@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Instalar AulaCoach sin internet
echo.
echo   Instalando AulaCoach en esta computadora. No necesita internet.
echo.
if not exist "instalador\paquetes" (
  echo   No encuentro la carpeta instalador. Primero prepare la USB con preparar_usb.bat
  goto :error
)
set "PYV=3.12"
if exist "instalador\python-version.txt" set /p PYV=<"instalador\python-version.txt"
set "PYDIR=%LOCALAPPDATA%\Programs\Python\Python%PYV:.=%"

rem --- 1. Python: la misma version para la que se bajaron los paquetes ---
set "PY="
py -%PYV% -c "import sys" >nul 2>nul && set "PY=py -%PYV%"
if defined PY goto :ollama
if exist "%PYDIR%\python.exe" set "PY="%PYDIR%\python.exe""
if defined PY goto :ollama
set "SETUP="
for %%f in ("instalador\python-*-amd64.exe") do set "SETUP=%%~ff"
if not defined SETUP (
  echo   Falta el instalador de Python en la carpeta instalador.
  goto :error
)
echo   Instalando Python %PYV%, tarda uno o dos minutos...
"%SETUP%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
if not exist "%PYDIR%\python.exe" (
  echo   No se pudo instalar Python. Abra el instalador con doble clic y vuelva a intentar.
  goto :error
)
set "PY="%PYDIR%\python.exe""

:ollama
rem --- 2. Ollama ---
where ollama >nul 2>nul && goto :paquetes
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" goto :paquetes
if not exist "instalador\OllamaSetup.exe" (
  echo   Falta OllamaSetup.exe en la carpeta instalador.
  goto :error
)
echo   Instalando Ollama: siga los pasos de la ventana que se abre.
start "" /wait "instalador\OllamaSetup.exe"

:paquetes
rem --- 3. Paquetes de Python y modelo, desde la USB ---
%PY% usb.py instalar
if errorlevel 1 goto :error
echo.
echo   Listo. Para usar AulaCoach: doble clic en iniciar.bat
echo.
pause
exit /b 0

:error
echo.
echo   La instalacion no termino. Revise el mensaje de arriba.
pause
exit /b 1
