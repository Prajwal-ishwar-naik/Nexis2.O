#!/usr/bin/env bash
# ==============================================================================
# Nexis AI - Production Multi-Server Cluster Launcher
# Concurrently launches 4 domain micro-servers + 1 Gateway Orchestrator
# Tracks process IDs in real-time, logs gateway output, and provides clean shutdown.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================================"
echo "⚡ NEXIS AI PRODUCTION MULTI-SERVER CLUSTER"
echo "Directory: $SCRIPT_DIR"
echo "======================================================================"

# 1. Port Cleanup: Kill any orphaned or zombie processes holding ports 8000-8004
echo "🧹 Cleaning stale ports 8000-8004..."
for port in {8000..8004}; do
  PIDS_ON_PORT=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$PIDS_ON_PORT" ]; then
    echo "   Reclaiming port $port (killing PID: $PIDS_ON_PORT)..."
    kill -9 $PIDS_ON_PORT 2>/dev/null || true
  fi
done
sleep 1

# 2. Python Virtual Environment Binding & Activation
VENV_ACTIVATE="$SCRIPT_DIR/venv/bin/activate"
if [ -f "$VENV_ACTIVATE" ]; then
    echo "🐍 Activating virtual environment: $VENV_ACTIVATE"
    source "$VENV_ACTIVATE"
    PYTHON_EXEC="$SCRIPT_DIR/venv/bin/python"
elif [ -f "$SCRIPT_DIR/../venv/bin/activate" ]; then
    echo "🐍 Activating parent virtual environment..."
    source "$SCRIPT_DIR/../venv/bin/activate"
    PYTHON_EXEC="$SCRIPT_DIR/../venv/bin/python"
else
    echo "⚠️ Warning: venv/bin/activate not found. Using system python3."
    PYTHON_EXEC="python3"
fi

# Verify critical dependencies
echo "🔍 Verifying critical dependencies..."
MISSING_DEPS=0
for pkg in fastapi uvicorn requests pydantic httpx groq; do
    if ! $PYTHON_EXEC -c "import $pkg" 2>/dev/null; then
        echo "❌ Critical dependency missing: $pkg"
        MISSING_DEPS=1
    fi
done

if [ $MISSING_DEPS -eq 1 ]; then
    echo "⚠️ Missing dependencies detected. Attempting fast pip install..."
    $PYTHON_EXEC -m pip install fastapi uvicorn requests pydantic httpx groq || {
        echo "❌ Dependency installation failed. Please run: pip install -r requirements.txt"
        exit 1
    }
fi
echo "✅ All critical dependencies verified."

declare -a PIDS=()
declare -a NAMES=()

cleanup() {
    echo ""
    echo "🛑 Received shutdown signal. Terminating Nexis AI cluster..."
    for i in "${!PIDS[@]}"; do
        pid="${PIDS[$i]}"
        name="${NAMES[$i]}"
        if kill -0 "$pid" 2>/dev/null; then
            echo "   Stopping $name (PID $pid)..."
            kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo "✅ All 5 servers cleanly stopped. Cluster terminated."
    exit 0
}

# Trap signals for clean exit
trap cleanup SIGINT SIGTERM EXIT

# 3. Launch 4 Domain Micro-Servers
echo ""
echo "🌾 [1/5] Starting Agri Micro-Server on Port 8001..."
$PYTHON_EXEC -m uvicorn agri_server:app --host 127.0.0.1 --port 8001 --log-level warning &
PID_AGRI=$!
PIDS+=($PID_AGRI)
NAMES+=("Agri-Server:8001")

echo "🏥 [2/5] Starting Health Micro-Server on Port 8002..."
$PYTHON_EXEC -m uvicorn health_server:app --host 127.0.0.1 --port 8002 --log-level warning &
PID_HEALTH=$!
PIDS+=($PID_HEALTH)
NAMES+=("Health-Server:8002")

echo "🎓 [3/5] Starting Education Micro-Server on Port 8003..."
$PYTHON_EXEC -m uvicorn edu_server:app --host 127.0.0.1 --port 8003 --log-level warning &
PID_EDU=$!
PIDS+=($PID_EDU)
NAMES+=("Edu-Server:8003")

echo "🏛️ [4/5] Starting Civic Welfare Micro-Server on Port 8004..."
$PYTHON_EXEC -m uvicorn civic_server:app --host 127.0.0.1 --port 8004 --log-level warning &
PID_CIVIC=$!
PIDS+=($PID_CIVIC)
NAMES+=("Civic-Server:8004")

# Allow domain micro-servers to bind sockets
sleep 1.5

# 4. Launch Gateway with Logging (Port 8000)
echo "🌐 [5/5] Starting Gateway Orchestrator on Port 8000 (logging to gateway.log)..."
$PYTHON_EXEC -m uvicorn gateway:app --host 127.0.0.1 --port 8000 --reload > gateway.log 2>&1 &
GATEWAY_PID=$!
PIDS+=($GATEWAY_PID)
NAMES+=("Gateway-Orchestrator:8000")
echo "Gateway started with PID $GATEWAY_PID on port 8000 (logging to gateway.log)"

# 5. Verification Probe Loop (up to 6 seconds)
echo "⏳ Probing Gateway readiness on http://127.0.0.1:8000..."
READY=0
for i in {1..12}; do
    if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1 || curl -s http://127.0.0.1:8000/ >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 0.5
done

if [ $READY -eq 1 ]; then
    echo "======================================================================"
    echo "🚀 CLUSTER ACTIVE & ACCEPTING CONNECTIONS:"
    echo "   - Port 8000 (Gateway):  PID $GATEWAY_PID  -> http://127.0.0.1:8000 (gateway.log)"
    echo "   - Port 8001 (Agri):     PID $PID_AGRI     -> http://127.0.0.1:8001"
    echo "   - Port 8002 (Health):   PID $PID_HEALTH   -> http://127.0.0.1:8002"
    echo "   - Port 8003 (Edu):      PID $PID_EDU      -> http://127.0.0.1:8003"
    echo "   - Port 8004 (Civic):    PID $PID_CIVIC    -> http://127.0.0.1:8004"
    echo "======================================================================"
    echo "Cluster Healthcheck: curl -s http://127.0.0.1:8000/health"
    echo "Press Ctrl+C to terminate all processes."
    echo "======================================================================"
else
    echo "❌ Gateway probe failed after 6 seconds. Inspecting last lines of gateway.log:"
    tail -n 25 gateway.log || true
fi

wait
