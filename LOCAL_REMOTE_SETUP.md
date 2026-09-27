# Local + Remote Tournament Setup

Run random tournaments **locally** with **Ollama Mistral**, connecting to a **remote game server**.

---

## Architecture

```
Your Local Machine                 Remote Server
═════════════════════════════════════════════════════════════
Ollama Mistral                     FastAPI Game Server
    ↓                                   ↑
random_tournament.py ───HTTP (API calls)─→ app/main.py
ollama_bot.py                                  ↓
    (4 bots per game)                    Game Logic
                                         (adjudication, etc.)
```

---

## Prerequisites

### Local Machine
- ✓ Python 3.8+
- ✓ Ollama installed (`ollama.ai`)
- ✓ Ollama Mistral model (`ollama pull mistral`)

### Remote Server
- ✓ FastAPI game server running
- ✓ Accessible via network (SSH tunnel or public IP)

---

## Quick Start

### Step 1: Start Ollama Locally

```bash
# Terminal 1: Start Ollama server (if not already running)
ollama serve

# Verify it's running
curl http://localhost:11434/api/tags
```

### Step 2: Start Remote Game Server

```bash
# Terminal 2 (on remote machine or via SSH)
ssh user@your-server.com

# On the remote server:
cd /path/to/micro-diplomacy
source venv/bin/activate
uvicorn app.main:app --port 8000 --host 0.0.0.0
```

**Note**: If using SSH tunnel instead:
```bash
# Local machine: Create SSH tunnel to remote server
ssh -L 8000:localhost:8000 user@your-server.com
# Then use http://localhost:8000 as server URL
```

### Step 3: Run Local Tournaments

```bash
# Terminal 3: Local tournament runner
cd /path/to/micro-diplomacy

# Run single random tournament
./run_local_tournaments.sh http://your-server.com:8000

# Run 10 random tournaments
./run_local_tournaments.sh http://your-server.com:8000 10

# Using SSH tunnel (if you created one)
./run_local_tournaments.sh http://localhost:8000 5
```

---

## Configuration

### Server URL

**Direct connection** (if server is public):
```bash
./run_local_tournaments.sh http://your-server.com:8000 5
```

**SSH tunnel** (more secure):
```bash
# Terminal A: Create tunnel
ssh -L 8000:localhost:8000 user@your-server.com

# Terminal B: Run tournaments
./run_local_tournaments.sh http://localhost:8000 5
```

**Local testing**:
```bash
./run_local_tournaments.sh http://localhost:8000 1
```

### Model Configuration

Currently hardcoded to use **Ollama Mistral**. To change:

Edit `run_local_tournaments.sh`:
```bash
python3 random_tournament.py \
    --model mistral \           # Change this line
    --base-url "$REMOTE_SERVER"
```

Available models (if installed):
- `mistral` (recommended, fast)
- `llama2`
- `neural-chat`
- `orca-mini`

Install additional models:
```bash
ollama pull llama2
ollama pull neural-chat
```

---

## Usage Examples

### Single Tournament Test
```bash
# Test with local server
chmod +x run_local_tournaments.sh
./run_local_tournaments.sh

# Test with remote server
./run_local_tournaments.sh http://your-server.com:8000
```

### Multiple Tournaments
```bash
# Run 5 tournaments
./run_local_tournaments.sh http://your-server.com:8000 5

# Run 20 tournaments (overnight)
nohup ./run_local_tournaments.sh http://your-server.com:8000 20 > tournaments.log 2>&1 &
```

### Monitor Progress
```bash
# Watch output in real-time
./run_local_tournaments.sh http://your-server.com:8000 10

# Or check logs
tail -f local_tournament_logs/tournaments_*.log
```

---

## Troubleshooting

### Ollama not found
```bash
# Install Ollama from ollama.ai
# Then verify:
ollama --version
ollama serve
```

### Ollama not running
```bash
Error: Ollama is not running on localhost:11434

# Fix: Start Ollama in another terminal
ollama serve

# Verify it's running
curl http://localhost:11434/api/tags
```

### Cannot reach remote server
```bash
Error: Cannot reach server at http://your-server.com:8000

# Check:
1. Is server running?
   ssh user@server "curl http://localhost:8000/api/v1/games"

2. Is port 8000 accessible?
   telnet your-server.com 8000

3. Use SSH tunnel instead:
   ssh -L 8000:localhost:8000 user@your-server.com
   # Then use http://localhost:8000
```

### Virtual environment not found
```bash
Error: Virtual environment not found

# Fix: Create and activate venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install httpx  # if needed
```

### Permission denied on script
```bash
chmod +x run_local_tournaments.sh
```

---

## Logs

Logs are saved to `local_tournament_logs/`:

```bash
# View all logs
ls -la local_tournament_logs/

# Watch live
tail -f local_tournament_logs/tournaments_*.log

# Extract winners
grep "Winner:" local_tournament_logs/tournaments_*.log | cut -d' ' -f3 | sort | uniq -c
```

---

## Advanced: Remote Server Setup via SSH

### One-time setup
```bash
# 1. SSH into your server
ssh user@your-server.com

# 2. Navigate to project
cd /path/to/micro-diplomacy
source venv/bin/activate

# 3. Create a startup script
cat > start_server.sh << 'EOF'
#!/bin/bash
source venv/bin/activate
uvicorn app.main:app --port 8000 --host 0.0.0.0
EOF
chmod +x start_server.sh
```

### Running the server
```bash
# Option A: Run in foreground (for testing)
ssh user@your-server.com "cd /path/to/micro-diplomacy && ./start_server.sh"

# Option B: Run in background with nohup
ssh user@your-server.com "cd /path/to/micro-diplomacy && nohup ./start_server.sh > server.log 2>&1 &"

# Option C: Run via screen (persistent)
ssh user@your-server.com "cd /path/to/micro-diplomacy && screen -S game-server -d -m ./start_server.sh"

# Check if running
ssh user@your-server.com "curl http://localhost:8000/api/v1/games"
```

### Creating an SSH tunnel
```bash
# Keep this running in a terminal
ssh -L 8000:localhost:8000 user@your-server.com

# In another terminal, run tournaments against localhost:8000
./run_local_tournaments.sh http://localhost:8000 10
```

---

## Performance Notes

### Local Machine Usage
- **CPU**: 20-40% per tournament (LLM inference)
- **Memory**: 300-500MB (Ollama + Python)
- **Network**: Minimal (just API calls)

### Network Latency Impact
- **Low latency** (<50ms): Imperceptible
- **Medium latency** (50-200ms): Small delays between phases
- **High latency** (>200ms): May hit phase timeouts

If latency is an issue, increase phase timeouts on the server.

---

## Tips

### Use SSH Key Authentication
```bash
# Avoid entering password repeatedly
ssh-copy-id user@your-server.com

# Then SSH without password
ssh user@your-server.com
```

### Keep Server Running 24/7
Use screen or systemd service on remote:

```bash
# Via screen (simple)
ssh user@server "screen -S game-server -d -m bash /path/to/start_server.sh"

# Check status
ssh user@server "screen -ls"

# Reattach to see output
ssh user@server "screen -r game-server"
```

### Monitor Both Machines
```bash
# Terminal 1: Ollama on local
ollama serve

# Terminal 2: Remote server (via SSH)
ssh -L 8000:localhost:8000 user@your-server.com

# Terminal 3: Local tournaments
./run_local_tournaments.sh http://localhost:8000 10

# Terminal 4: Monitor local system
watch -n 1 'ps aux | grep -E "ollama|python" | grep -v grep'
```

---

## Common Workflows

### Daily Testing (Morning)
```bash
# Check server is reachable
./run_local_tournaments.sh http://your-server.com:8000 1

# Run 5 tournaments
./run_local_tournaments.sh http://your-server.com:8000 5

# Check results
tail -20 local_tournament_logs/tournaments_*.log
```

### Overnight Data Collection
```bash
# Run 100 tournaments (takes ~6-7 hours)
nohup ./run_local_tournaments.sh http://your-server.com:8000 100 > tournaments.log 2>&1 &

# Next morning, analyze results
grep "Winner:" local_tournament_logs/tournaments_*.log | wc -l  # Should be ~100
```

### Development/Testing
```bash
# Run single tournament to test changes
./run_local_tournaments.sh http://localhost:8000 1

# Then run batch
./run_local_tournaments.sh http://localhost:8000 10
```

---

## Next Steps

1. **Ensure Ollama is running**: `ollama serve`
2. **Ensure remote server is running**: `uvicorn app.main:app --port 8000 --host 0.0.0.0`
3. **Test connection**: `./run_local_tournaments.sh http://your-server.com:8000 1`
4. **Run tournaments**: `./run_local_tournaments.sh http://your-server.com:8000 10`

Your local + remote setup is ready! 🚀
