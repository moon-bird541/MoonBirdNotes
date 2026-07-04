@echo off
setlocal

cd /d "%~dp0backend"
"%~dp0.venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000

echo.
echo Backend process has stopped.
pause
