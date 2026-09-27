#!/bin/bash

# Local Tournament Runner
# Runs random tournaments locally, connecting to remote game server
# Uses local Ollama Mistral for LLM inference

set -e

# Configuration
REMOTE_SERVER="${1:-http://localhost:8000}"
NUM_TOURNAMENTS="${2:-1}"
WORK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$WORK_DIR/venv"
LOG_DIR="$WORK_DIR/local_tournament_logs"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Create log directory
mkdir -p "$LOG_DIR"

# Verify Ollama is running
check_ollama() {
    if ! command -v ollama &> /dev/null; then
        echo -e "${RED}Error: Ollama not found. Please install Ollama.${NC}"
        exit 1
    fi

    # Try to ping ollama (typically runs on localhost:11434)
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${RED}Error: Ollama is not running on localhost:11434${NC}"
        echo "Start Ollama with: ollama serve"
        exit 1
    fi

    echo -e "${GREEN}✓ Ollama is running${NC}"
}

# Verify server is reachable
check_server() {
    if ! curl -s "$REMOTE_SERVER/api/v1/games" > /dev/null 2>&1; then
        echo -e "${RED}Error: Cannot reach server at $REMOTE_SERVER${NC}"
        echo "Make sure the server is running:"
        echo "  ssh user@server 'cd /path/to/micro-diplomacy && uvicorn app.main:app --port 8000'"
        exit 1
    fi

    echo -e "${GREEN}✓ Server is reachable at $REMOTE_SERVER${NC}"
}

# Source virtual environment
setup_venv() {
    if [ ! -f "$VENV/bin/activate" ]; then
        echo -e "${RED}Error: Virtual environment not found at $VENV${NC}"
        exit 1
    fi

    source "$VENV/bin/activate"
    echo -e "${GREEN}✓ Virtual environment activated${NC}"
}

# Run tournaments
run_tournaments() {
    cd "$WORK_DIR"

    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}LOCAL RANDOM TOURNAMENTS${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo "Remote Server: $REMOTE_SERVER"
    echo "LLM Model: Ollama Mistral (local)"
    echo "Tournaments: $NUM_TOURNAMENTS"
    echo ""

    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    LOG_FILE="$LOG_DIR/tournaments_${TIMESTAMP}.log"

    if [ "$NUM_TOURNAMENTS" -eq 1 ]; then
        python3 random_tournament.py \
            --model mistral \
            --base-url "$REMOTE_SERVER" \
            | tee "$LOG_FILE"
    else
        python3 random_tournament.py \
            --model mistral \
            --base-url "$REMOTE_SERVER" \
            --num "$NUM_TOURNAMENTS" \
            | tee "$LOG_FILE"
    fi

    echo ""
    echo -e "${GREEN}✓ Tournaments complete. Log saved to: $LOG_FILE${NC}"
}

# Main
main() {
    echo -e "${BLUE}Local Tournament Runner${NC}"
    echo ""

    # Checks
    echo "Checking prerequisites..."
    check_ollama
    check_server
    setup_venv

    # Run
    run_tournaments
}

main
