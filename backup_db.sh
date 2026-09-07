#!/bin/bash
APP_DIR="/home/$USER/micro-diplomacy"
DB_FILE="$APP_DIR/diplobucks.db"
BACKUP_DIR="$APP_DIR/backups"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.db"

mkdir -p "$BACKUP_DIR"
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"
gzip "$BACKUP_FILE"
find "$BACKUP_DIR" -type f -name "*.db.gz" -mtime +7 -exec rm {} \;
