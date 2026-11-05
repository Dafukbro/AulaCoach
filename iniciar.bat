@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title AulaCoach
echo.
echo   Iniciando AulaCoach...
echo.
echo   Los docentes entran desde su celular, conectados al Wi-Fi de la escuela, a la
echo   direccion que aparece abajo como "Network URL".
echo.
echo   No cierres esta ventana mientras se use AulaCoach.
echo.

rem Si Ollama no esta abierto, se abre (sin internet).
tasklist /fi "imagename eq ollama.exe" 2>nul | find /i "ollama.exe" >nul
if errorlevel 1 if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"

rem El Python que tiene AulaCoach instalado (el de la USB es el 3.12).
set "PY=python"
python -c "import streamlit" >nul 2>nul && goto :arrancar
py -3.12 -c "import streamlit" >nul 2>nul && set "PY=py -3.12"

:arrancar
rem Si quedo una sesion anterior de AulaCoach usando el puerto 8501, se cierra primero.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8501 " ^| findstr "LISTENING"') do taskkill /F /PID %%p >nul 2>nul
%PY% -m streamlit run app.py
pause
