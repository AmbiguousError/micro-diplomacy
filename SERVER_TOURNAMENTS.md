# Server-Side Random Tournament Runner

Run continuous, automated tournaments on your server with random persona selections.

---

## Quick Start (3 Steps)

### 1. Install Service (One-Time)
```bash
sudo /home/g/Documents/micro-diplomacy/manage_tournament.sh install
```

### 2. Start Tournaments (Infinite)
```bash
sudo /home/g/Documents/micro-diplomacy/manage_tournament.sh start
```

### 3. Monitor Progress
```bash
# Check status
/home/g/Documents/micro-diplomacy/manage_tournament.sh status

# Watch live logs
/home/g/Documents/micro-diplomacy/manage_tournament.sh logs

# See summary
/home/g/Documents/micro-diplomacy/manage_tournament.sh summary
```

---

## What's Included

### Files Created

1. **`run_tournaments.sh`** — Executes random tournaments in a loop
   - Runs infinite tournaments by default
   - Or runs N tournaments then exits
   - Logs each game to timestamped files
   - Graceful shutdown on SIGTERM

2. **`micro-diplomacy-tournament.service`** — systemd service file
   - Runs as background daemon
   - Auto-restarts on failure
   - Starts on server boot
   - Resource limits (2GB RAM, 80% CPU)
   - Journal logging

3. **`manage_tournament.sh`** — Management interface
   - Install/start/stop service
   - View status and logs
   - Clean old log files
   - Run local tests

---

## Management Commands

### Installation & Control

```bash
# Install service (requires sudo)
sudo manage_tournament.sh install

# Start tournaments (requires sudo)
sudo manage_tournament.sh start

# Stop tournaments (requires sudo)
sudo manage_tournament.sh stop

# Restart service (requires sudo)
sudo manage_tournament.sh restart
```

### Monitoring

```bash
# Show service status
manage_tournament.sh status

# Watch live logs (Ctrl+C to exit)
manage_tournament.sh logs

# Show tournament summary
manage_tournament.sh summary
```

### Maintenance

```bash
# Clean old logs (keeps last 30)
manage_tournament.sh clean

# Run single tournament locally (for testing)
manage_tournament.sh run-local

# Run N tournaments locally
manage_tournament.sh run-n 5
```

---

## How It Works

### Service Architecture

```
systemd (micro-diplomacy-tournament.service)
    ↓
run_tournaments.sh (infinite loop)
    ↓
random_tournament.py (picks 4 random personas)
    ↓
tournament_runner.py (runs game)
    ↓
Logs: tournament_logs/tournament_YYYYMMDD_HHMMSS.log
```

### Game Flow

1. Service starts → Loads virtual environment
2. Each iteration:
   - Selects 4 random personas
   - Runs tournament (~3-4 minutes)
   - Logs winner and game details
   - Repeats

### Log Files

```
tournament_logs/
  ├── tournament_20250927_142300.log    # Individual game logs
  ├── tournament_20250927_142700.log
  ├── tournament_20250927_143100.log
  └── summary.log                       # All games summary
```

---

## Monitoring & Logs

### Check Service Status
```bash
sudo systemctl status micro-diplomacy-tournament
```

Output:
```
● micro-diplomacy-tournament.service - Micro-Diplomacy Random Tournament Server
     Loaded: loaded (/etc/systemd/system/micro-diplomacy-tournament.service; enabled)
     Active: active (running) since Sun 2025-09-27 14:00:00 UTC; 2h 30min ago
   Process: 12345 ExecStart=/bin/bash /home/g/.../run_tournaments.sh 0
  Main PID: 12346 (bash)
    Memory: 125.5M
       CPU: 45%
```

### View Summary
```bash
manage_tournament.sh summary
```

Output:
```
Tournament Summary
════════════════════════════════════════
Total games run: 42

Recent tournaments:
[2025-09-27 14:23:45] Running tournament #42...
[2025-09-27 14:20:12] Running tournament #41...
[2025-09-27 14:16:38] Running tournament #40...
```

### Watch Live Logs
```bash
manage_tournament.sh logs
```

Streams live tournament starts and winners:
```
[2025-09-27 14:23:45] Running tournament #42...
[2025-09-27 14:27:30] Running tournament #43...
[2025-09-27 14:31:15] Running tournament #44...
...
```

---

## Resource Usage

### Typical Resource Consumption

- **Memory**: 150-300MB per game
- **CPU**: 40-60% during game
- **Disk**: ~2MB per game log
- **Network**: Minimal (localhost API calls)

### Performance Metrics

- **Game Duration**: 3-4 minutes (with 10s phases)
- **Throughput**: 15-20 games per hour
- **24-Hour Output**: ~360 games, ~700MB logs

---

## Advanced Usage

### Run N Tournaments Then Exit
```bash
# Via local execution
manage_tournament.sh run-n 10

# Via systemd (custom)
systemctl start --no-block micro-diplomacy-tournament
```

### Adjust Resource Limits
Edit `/etc/systemd/system/micro-diplomacy-tournament.service`:

```ini
[Service]
MemoryLimit=4G          # Increase to 4GB
CPUQuota=100%          # Use full CPU
```

Then reload:
```bash
sudo systemctl daemon-reload
sudo systemctl restart micro-diplomacy-tournament
```

### View Journal Logs
```bash
# Last 50 lines
sudo journalctl -u micro-diplomacy-tournament -n 50 --no-pager

# Follow live
sudo journalctl -u micro-diplomacy-tournament -f

# Since specific time
sudo journalctl -u micro-diplomacy-tournament --since "2 hours ago"
```

### Manual Tournament Run (No Service)
```bash
cd /home/g/Documents/micro-diplomacy
source venv/bin/activate
bash run_tournaments.sh 10    # Run 10 tournaments
```

---

## Troubleshooting

### Service won't start
```bash
# Check error
sudo systemctl status micro-diplomacy-tournament
sudo journalctl -u micro-diplomacy-tournament -n 20 --no-pager

# Try manual run to debug
bash /home/g/Documents/micro-diplomacy/run_tournaments.sh 1
```

### Out of disk space
```bash
# Clean old logs
manage_tournament.sh clean

# Check disk usage
du -sh /home/g/Documents/micro-diplomacy/tournament_logs/

# Remove old logs manually if needed
ls -1t tournament_logs/tournament_*.log | tail -n +31 | xargs rm
```

### Games running slowly
```bash
# Check system load
top -bn1 | head -20

# Check if server is running
curl http://localhost:8000/api/v1/games

# Verify game speed (should be ~3-4 min)
manage_tournament.sh summary
```

### Tournament script errors
```bash
# Check Python errors
tail -50 /home/g/Documents/micro-diplomacy/tournament_logs/tournament_*.log

# Run single test game
manage_tournament.sh run-local

# Check prompts.yaml is valid
python3 -c "import yaml; yaml.safe_load(open('prompts.yaml'))"
```

---

## Maintenance

### Daily Tasks
```bash
# Check status
manage_tournament.sh status

# View summary
manage_tournament.sh summary
```

### Weekly Tasks
```bash
# Clean old logs
manage_tournament.sh clean

# Check disk usage
du -sh tournament_logs/
```

### Monthly Tasks
```bash
# Archive old logs (optional)
tar czf tournament_logs_backup_$(date +%Y%m).tar.gz tournament_logs/

# Restart service to clear any memory leaks
sudo systemctl restart micro-diplomacy-tournament
```

---

## Data Collection

### Analyze Results
Extract winners from all games:
```bash
grep "Winner:" tournament_logs/summary.log | cut -d' ' -f3 | sort | uniq -c
```

Output:
```
     12 Red
     11 Blue
      9 Yellow
      8 Green
      2 Red/Blue
```

### Track Personas Used
Extract which personas competed:
```bash
grep "RANDOM TOURNAMENT:" tournament_logs/summary.log | \
  cut -d':' -f4 | sort | uniq -c | sort -rn
```

### Performance Trending
Track games per hour over time:
```bash
for hour in {0..23}; do
  COUNT=$(grep -c "$(date -d '-1 hour +%H')" tournament_logs/summary.log)
  echo "Hour $hour: $COUNT games"
done
```

---

## Typical Workflow

### Day 1: Setup
```bash
# Install service
sudo manage_tournament.sh install

# Start tournaments
sudo manage_tournament.sh start

# Verify it's running
manage_tournament.sh status
```

### Day 2-7: Monitor
```bash
# Each morning, check summary
manage_tournament.sh summary

# Weekly cleanup
manage_tournament.sh clean
```

### End of Week: Analysis
```bash
# Extract all results
grep "Winner:" tournament_logs/summary.log | cut -d' ' -f3 | sort | uniq -c

# Identify strongest personas
# (Persona that appears most in winning factions)
```

---

## Example Output

### Status Check
```
Tournament Service Status
════════════════════════════════════════
● micro-diplomacy-tournament.service - Micro-Diplomacy Random Tournament Server
     Loaded: loaded (/etc/systemd/system/micro-diplomacy-tournament.service; enabled)
     Active: active (running) since Sun 2025-09-27 12:00:00 UTC; 5h 30min ago
   Process: 12345 ExecStart=/bin/bash /home/g/.../run_tournaments.sh
  Main PID: 12346
    Memory: 245.3M
       CPU: 52%

Log Directory: /home/g/Documents/micro-diplomacy/tournament_logs
Games logged: 98

Recent Activity:
[2025-09-27 17:30:45] Running tournament #98...
[2025-09-27 17:27:12] Running tournament #97...
[2025-09-27 17:23:38] Running tournament #96...
[2025-09-27 17:20:05] Running tournament #95...
[2025-09-27 17:16:32] Running tournament #94...
```

---

## Next Steps

1. **Install**: `sudo manage_tournament.sh install`
2. **Start**: `sudo manage_tournament.sh start`
3. **Monitor**: `manage_tournament.sh status`
4. **Collect Data**: Review logs and analyze tournament outcomes
5. **Iterate**: Adjust personas or timing as needed based on results

Your server is now running continuous random tournaments! 🚀
