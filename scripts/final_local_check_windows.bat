@echo off
setlocal
cd /d "%~dp0.."

echo == Backend tests ==
cd backend
pytest -q
if errorlevel 1 exit /b 1

echo == Benchmark audit ==
set PYTHONPATH=.
python tools\run_phase20_benchmark_audit.py
if errorlevel 1 exit /b 1

echo == Chrono validation harness ==
python tools\chrono_validation\run_all_validations.py --strict
if errorlevel 1 exit /b 1

echo == Release candidate audit ==
python tools\run_release_candidate_audit.py
if errorlevel 1 exit /b 1

cd ..

echo == Frontend build check ==
call scripts\check_frontend_build_windows.bat
if errorlevel 2 (
  echo Frontend build check skipped because dependencies are not installed.
  echo Run: cd frontend ^&^& npm install ^&^& npm run build
  exit /b 0
)
if errorlevel 1 exit /b 1

echo Final local check passed.
