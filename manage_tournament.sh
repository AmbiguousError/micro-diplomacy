#!/bin/bash

# Tournament Service Manager
# Easy commands to start/stop/monitor tournaments on the server

set -e

SERVICE_NAME="micro-diplomacy-tournament"
SERVICE_FILE="/home/g/Documents/micro-diplomacy/$SERVICE_NAME.service"
LOG_DIR="/home/g/Documents/micro-diplomacy/tournament_logs"
SYSTEMD_DIR="/etc/systemd/system"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

usage() {
    cat << EOF
Usage: $0 <command>

Commands:
  install       Install tournament service (requires sudo)
  start         Start tournament service (requires sudo)
  stop          Stop tournament service (requires sudo)
  restart       Restart tournament service (requires sudo)
  status        Show service status
  logs          Show live tournament logs
  summary       Show tournament summary
  clean         Clean old log files (keeps last 30)
  run-local     Run single tournament locally (for testing)
  run-n <N>     Run N tournaments locally (for testing)

Examples:
  sudo $0 install                # Set up service
  sudo $0 start                  # Start running tournaments
  $0 status                      # Check if running
  $0 logs                        # Watch live logs
  $0 summary                     # Show results summary
  sudo $0 stop                   # Stop tournaments

EOF
    exit 1
}

# Ensure log directory exists
mkdir -p "$LOG_DIR"

install_service() {
    echo -e "${BLUE}Installing tournament service...${NC}"

    if [ ! -f "$SERVICE_FILE" ]; then
        echo -e "${RED}Error: Service file not found at $SERVICE_FILE${NC}"
        exit 1
    fi

    # Copy service file to systemd
    sudo cp "$SERVICE_FILE" "$SYSTEMD_DIR/"
    sudo chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME.service"

    # Reload systemd
    sudo systemctl daemon-reload

    # Enable service to start on boot
    sudo systemctl enable "$SERVICE_NAME.service"

    echo -e "${GREEN}✓ Service installed successfully${NC}"
    echo ""
    echo "Next steps:"
    echo "  sudo systemctl start $SERVICE_NAME"
    echo "  systemctl status $SERVICE_NAME"
}

start_service() {
    echo -e "${BLUE}Starting tournament service...${NC}"
    sudo systemctl start "$SERVICE_NAME.service"
    echo -e "${GREEN}✓ Service started${NC}"
    sleep 1
    systemctl status "$SERVICE_NAME.service" --no-pager
}

stop_service() {
    echo -e "${YELLOW}Stopping tournament service...${NC}"
    sudo systemctl stop "$SERVICE_NAME.service"
    echo -e "${GREEN}✓ Service stopped${NC}"
}

restart_service() {
    echo -e "${YELLOW}Restarting tournament service...${NC}"
    sudo systemctl restart "$SERVICE_NAME.service"
    echo -e "${GREEN}✓ Service restarted${NC}"
    sleep 1
    systemctl status "$SERVICE_NAME.service" --no-pager
}

show_status() {
    echo -e "${BLUE}Tournament Service Status${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    systemctl status "$SERVICE_NAME.service" --no-pager
    echo ""
    echo -e "${BLUE}Log Directory: $LOG_DIR${NC}"

    if [ -d "$LOG_DIR" ]; then
        GAME_COUNT=$(ls -1 "$LOG_DIR"/tournament_*.log 2>/dev/null | wc -l)
        echo "Games logged: $GAME_COUNT"

        if [ -f "$LOG_DIR/summary.log" ]; then
            echo ""
            echo -e "${BLUE}Recent Activity:${NC}"
            tail -5 "$LOG_DIR/summary.log"
        fi
    fi
}

show_logs() {
    echo -e "${BLUE}Tournament Logs (Ctrl+C to exit)${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ ! -f "$LOG_DIR/summary.log" ]; then
        echo -e "${YELLOW}No logs yet. Service may not be running.${NC}"
        exit 1
    fi

    tail -f "$LOG_DIR/summary.log"
}

show_summary() {
    echo -e "${BLUE}Tournament Summary${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ ! -f "$LOG_DIR/summary.log" ]; then
        echo -e "${YELLOW}No games run yet.${NC}"
        exit 1
    fi

    TOTAL_GAMES=$(cat "$LOG_DIR/summary.log" | grep "Running tournament" | wc -l)
    echo "Total games run: $TOTAL_GAMES"
    echo ""
    echo "Recent tournaments:"
    cat "$LOG_DIR/summary.log" | tail -20

    if [ -d "$LOG_DIR" ]; then
        echo ""
        echo "Detailed logs available:"
        ls -1t "$LOG_DIR"/tournament_*.log 2>/dev/null | head -5 | sed 's/^/  /'
    fi
}

clean_logs() {
    echo -e "${YELLOW}Cleaning old log files (keeping last 30)...${NC}"

    if [ ! -d "$LOG_DIR" ]; then
        echo -e "${YELLOW}No log directory found.${NC}"
        exit 0
    fi

    # Count files
    FILE_COUNT=$(ls -1 "$LOG_DIR"/tournament_*.log 2>/dev/null | wc -l)

    if [ "$FILE_COUNT" -le 30 ]; then
        echo "Only $FILE_COUNT files, nothing to clean."
        exit 0
    fi

    # Remove oldest files, keeping 30
    FILES_TO_DELETE=$((FILE_COUNT - 30))
    ls -1t "$LOG_DIR"/tournament_*.log 2>/dev/null | tail -$FILES_TO_DELETE | xargs rm -f

    echo -e "${GREEN}✓ Deleted $FILES_TO_DELETE old log files${NC}"
}

run_local() {
    echo -e "${BLUE}Running single tournament locally...${NC}"
    echo ""
    cd /home/g/Documents/micro-diplomacy
    source venv/bin/activate
    python3 random_tournament.py
}

run_n_local() {
    if [ -z "$1" ]; then
        echo "Error: Specify number of tournaments"
        exit 1
    fi

    echo -e "${BLUE}Running $1 tournament(s) locally...${NC}"
    echo ""
    cd /home/g/Documents/micro-diplomacy
    source venv/bin/activate
    python3 random_tournament.py --num "$1"
}

# Main command routing
case "${1:-}" in
    install)
        install_service
        ;;
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs
        ;;
    summary)
        show_summary
        ;;
    clean)
        clean_logs
        ;;
    run-local)
        run_local
        ;;
    run-n)
        run_n_local "$2"
        ;;
    *)
        usage
        ;;
esac
