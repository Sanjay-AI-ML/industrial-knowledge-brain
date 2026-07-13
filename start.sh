#!/usr/bin/env bash
set -e

echo "====================================================================="
echo "                Industrial Knowledge Brain (IKB)"
echo "                     Launch & Setup Utility"
echo "====================================================================="
echo

echo "[1] Run via Docker Compose (Recommended — one command, bundles Neo4j)"
echo "[2] Run locally (Requires Python, Node.js, and npm installed)"
echo "[3] Exit"
echo
read -p "Select an option (1-3): " choice

if [ "$choice" = "1" ]; then
    if [ ! -f ".env" ]; then
        echo "[INFO] Root .env not found. Creating from .env.example..."
        cp ".env.example" ".env"
        echo "[WARN] Edit .env in the project root and set GEMINI_API_KEY, then re-run this script."
        exit 1
    fi
    if grep -q "GEMINI_API_KEY=REPLACE_ME" ".env"; then
        echo "[WARN] GEMINI_API_KEY is still REPLACE_ME in .env — edit it before continuing."
        exit 1
    fi
    echo
    echo "[INFO] Starting services via Docker Compose (backend, frontend, bundled Neo4j)..."
    docker compose up --build
elif [ "$choice" = "2" ]; then
    if [ ! -f ".env" ]; then
        echo "[INFO] Root .env not found. Creating from .env.example..."
        cp ".env.example" ".env"
        echo "[WARN] Edit .env in the project root and set GEMINI_API_KEY (and NEO4J_* if not running Neo4j locally)."
    fi
    if grep -q "GEMINI_API_KEY=REPLACE_ME" ".env"; then
        echo "[WARN] GEMINI_API_KEY is still REPLACE_ME in .env — edit it before continuing."
        exit 1
    fi

    echo "[INFO] Installing backend dependencies..."
    cd backend
    python3 -m pip install -r requirements.txt

    echo "[INFO] Starting backend server in background..."
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!

    cd ../frontend
    echo "[INFO] Installing frontend dependencies..."
    npm install

    echo "[INFO] Starting frontend server..."
    npm run dev

    trap "kill $BACKEND_PID" EXIT
else
    exit 0
fi
