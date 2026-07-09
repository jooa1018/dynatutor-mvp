@echo off
setlocal
cd /d "%~dp0..\frontend"

where node >nul 2>nul
if errorlevel 1 (
  echo node is not installed. Install Node.js 20+ first.
  exit /b 2
)

where npm >nul 2>nul
if errorlevel 1 (
  echo npm is not installed. Install npm first.
  exit /b 2
)

echo [frontend-build] npm ci
npm ci
if errorlevel 1 exit /b 1

python "%~dp0check_frontend_build.py"
if errorlevel 1 exit /b %errorlevel%
