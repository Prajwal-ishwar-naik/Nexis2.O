@echo off
REM ==============================================================================
REM Nexis AI - Production Multi-Server Cluster Launcher (Windows)
REM Concurrently launches 4 domain micro-servers + 1 Gateway Orchestrator
REM ==============================================================================

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
    set PYTHON_EXEC="%SCRIPT_DIR%venv\Scripts\python.exe"
) else (
    set PYTHON_EXEC=python
)

echo ======================================================================
echo Launching Nexis AI Multi-Server Cluster...
echo Using Python runtime: %PYTHON_EXEC%
echo ======================================================================

echo [1/5] Launching Agri Micro-Server on Port 8001...
start "Agri Server :8001" %PYTHON_EXEC% -m uvicorn agri_server:app --host 127.0.0.1 --port 8001 --log-level info

echo [2/5] Launching Health Micro-Server on Port 8002...
start "Health Server :8002" %PYTHON_EXEC% -m uvicorn health_server:app --host 127.0.0.1 --port 8002 --log-level info

echo [3/5] Launching Education Micro-Server on Port 8003...
start "Edu Server :8003" %PYTHON_EXEC% -m uvicorn edu_server:app --host 127.0.0.1 --port 8003 --log-level info

echo [4/5] Launching Civic Welfare Micro-Server on Port 8004...
start "Civic Server :8004" %PYTHON_EXEC% -m uvicorn civic_server:app --host 127.0.0.1 --port 8004 --log-level info

timeout /t 2 /nobreak >nul

echo [5/5] Launching Gateway Orchestrator on Port 8000...
start "Gateway Orchestrator :8000" %PYTHON_EXEC% -m uvicorn gateway:app --host 127.0.0.1 --port 8000 --log-level info

echo ======================================================================
echo Cluster launched successfully across ports 8000, 8001, 8002, 8003, 8004.
echo Close individual console windows to terminate servers.
echo ======================================================================
pause
