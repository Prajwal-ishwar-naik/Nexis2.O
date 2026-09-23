#!/usr/bin/env bash
# ==============================================================================
# Nexis AI - Production Multi-Server Cluster Launcher
# Concurrently launches 4 domain micro-servers + 1 Gateway Orchestrator
# Tracks process IDs in real-time and provides graceful shutdown.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Locate virtual environment python binary
if [ -f "$SCRIPT_DIR/venv/bin/python" ]; then
    PYTHON_EXEC="$SCRIPT_DIR/venv/bin/python"
elif [ -f "$SCRIPT_DIR/../venv/bin/python" ]; then
    PYTHON_EXEC="$SCRIPT_DIR/../venv/bin/python"
else
    PYTHON_EXEC="python3"
fi

echo "======================================================================"
echo "⚡ NEXIS AI PRODUCTION MULTI-SERVER RUNTIME"
echo "Python Runtime: $PYTHON_EXEC"
echo "Directory:      $SCRIPT_DIR"
echo "======================================================================"

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

# 1. Agri Micro-Server (Port 8001)
echo "🌾 [1/5] Starting Agri Micro-Server on Port 8001..."
$PYTHON_EXEC -m uvicorn agri_server:app --host 127.0.0.1 --port 8001 --log-level info &
PID_AGRI=$!
PIDS+=($PID_AGRI)
NAMES+=("Agri-Server:8001")

# 2. Health Micro-Server (Port 8002)
echo "🏥 [2/5] Starting Health Micro-Server on Port 8002..."
$PYTHON_EXEC -m uvicorn health_server:app --host 127.0.0.1 --port 8002 --log-level info &
PID_HEALTH=$!
PIDS+=($PID_HEALTH)
NAMES+=("Health-Server:8002")

# 3. Education Micro-Server (Port 8003)
echo "🎓 [3/5] Starting Education Micro-Server on Port 8003..."
$PYTHON_EXEC -m uvicorn edu_server:app --host 127.0.0.1 --port 8003 --log-level info &
PID_EDU=$!
PIDS+=($PID_EDU)
NAMES+=("Edu-Server:8003")

# 4. Civic Welfare Micro-Server (Port 8004)
echo "🏛️ [4/5] Starting Civic Welfare Micro-Server on Port 8004..."
$PYTHON_EXEC -m uvicorn civic_server:app --host 127.0.0.1 --port 8004 --log-level info &
PID_CIVIC=$!
PIDS+=($PID_CIVIC)
NAMES+=("Civic-Server:8004")

# Allow domain micro-servers to bind sockets
sleep 2

# 5. Gateway Orchestrator (Port 8000)
echo "🌐 [5/5] Starting Gateway Orchestrator on Port 8000..."
$PYTHON_EXEC -m uvicorn gateway:app --host 127.0.0.1 --port 8000 --log-level info &
PID_GATEWAY=$!
PIDS+=($PID_GATEWAY)
NAMES+=("Gateway-Orchestrator:8000")

echo "======================================================================"
echo "🚀 CLUSTER DEPLOYED SUCCESSFULLY ACROSS 5 PORTS:"
echo "   - Port 8000 (Gateway):  PID $PID_GATEWAY  -> http://127.0.0.1:8000"
echo "   - Port 8001 (Agri):     PID $PID_AGRI     -> http://127.0.0.1:8001"
echo "   - Port 8002 (Health):   PID $PID_HEALTH   -> http://127.0.0.1:8002"
echo "   - Port 8003 (Edu):      PID $PID_EDU      -> http://127.0.0.1:8003"
echo "   - Port 8004 (Civic):    PID $PID_CIVIC    -> http://127.0.0.1:8004"
echo "======================================================================"
echo "Cluster Healthcheck: curl -s http://127.0.0.1:8000/api/system/health"
echo "Press Ctrl+C to terminate all processes."
echo "======================================================================"

wait
