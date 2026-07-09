@echo off
echo DynaTutor Local Study Mode
echo Backend and frontend will open in separate windows.
start "DynaTutor Backend" cmd /k "cd /d %~dp0..\backend && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000"
start "DynaTutor Frontend" cmd /k "cd /d %~dp0..\frontend && npm install && npm run dev"
echo Open http://localhost:3000 after both servers start.
