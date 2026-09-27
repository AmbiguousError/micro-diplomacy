#!/bin/bash

# Random Tournament Server Runner
# Runs continuous random tournaments on the server
# Logs output to timestamped files for monitoring

set -e

WORK_DIR="/home/g/Documents/micro-diplomacy"
LOG_DIR="$WORK_DIR/tournament_logs"
VENV="$WORK_DIR/venv"

# Create log directory
mkdir -p "$LOG_DIR"

# Source virtual environment
source "$VENV/bin/activate"

# Get number of tournaments to run (default: infinite)
NUM_TOURNAMENTS=${1:-0}  # 0 means infinite loop

# Function to run tournaments
run_tournaments() {
    if [ "$NUM_TOURNAMENTS" -eq 0 ]; then
        # Infinite mode
        echo "Starting infinite tournament mode..."
        while true; do
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            LOG_FILE="$LOG_DIR/tournament_$TIMESTAMP.log"
            echo "[$(date)] Running random tournament #$((++GAME_COUNT))..." | tee -a "$LOG_DIR/summary.log"
            python3 "$WORK_DIR/random_tournament.py" >> "$LOG_FILE" 2>&1
            sleep 2  # Brief pause between tournaments
        done
    else
        # Run N tournaments then exit
        echo "Starting $NUM_TOURNAMENTS tournament(s)..."
        for i in $(seq 1 $NUM_TOURNAMENTS); do
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            LOG_FILE="$LOG_DIR/tournament_${TIMESTAMP}_${i}.log"
            echo "[$(date)] Running tournament $i/$NUM_TOURNAMENTS..." | tee -a "$LOG_DIR/summary.log"
            python3 "$WORK_DIR/random_tournament.py" >> "$LOG_FILE" 2>&1
            sleep 2
        done
        echo "[$(date)] Completed $NUM_TOURNAMENTS tournament(s)" | tee -a "$LOG_DIR/summary.log"
    fi
}

# Trap signals for graceful shutdown
trap 'echo "[$(date)] Tournament runner stopped" | tee -a "$LOG_DIR/summary.log"; exit 0' SIGTERM SIGINT

# Start tournaments
cd "$WORK_DIR"
run_tournaments
