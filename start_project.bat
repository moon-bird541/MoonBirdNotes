@echo off
setlocal

if not exist "%~dp0start_backend.bat" (
    echo [ERROR] start_backend.bat not found.
    pause
    exit /b 1
)

if not exist "%~dp0start_frontend.bat" (
    echo [ERROR] start_frontend.bat not found.
    pause
    exit /b 1
)

start "MoonBirdNotes Backend" "%~dp0start_backend.bat"
start "MoonBirdNotes Frontend" "%~dp0start_frontend.bat"

echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo Keep the two new windows open while using the project.
pause
