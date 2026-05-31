@echo off
setlocal

cd /d "%~dp0frontend\moonsbirdnotrs_vue"
npm.cmd run dev -- --host 127.0.0.1 --port 5173

echo.
echo Frontend process has stopped.
pause
