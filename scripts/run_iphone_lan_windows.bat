@echo off
echo DynaTutor iPhone 14 LAN Mode
echo Make sure your iPhone and PC are on the same Wi-Fi.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do set IP=%%a
set IP=%IP: =%
echo Open this on iPhone Safari: http://%IP%:3000
echo Then tap Share - Add to Home Screen.
start "DynaTutor Backend LAN" cmd /k "cd /d %~dp0..\backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
start "DynaTutor Frontend LAN" cmd /k "cd /d %~dp0..\frontend && npm install && npm run dev -- -H 0.0.0.0"
