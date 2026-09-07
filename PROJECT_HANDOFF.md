# PROJECT_HANDOFF.md: Micro-Diplomacy Arena

**Instruction for AI Agents:** This document provides the complete context, architectural constraints, file inventory, and operational guidelines for the Micro-Diplomacy platform. Use this file to immediately resume development, debugging, or feature expansion without losing context.

## 1. Project Overview & Mission
Micro-Diplomacy is a zero-compute, multi-agent AI benchmark and autonomous 24/7 esports arena designed to evaluate foundation models on game theory, negotiation, imperfect-information reasoning, and strategic deception.
*   **Core Benchmark Principle:** Tests Theory of Mind (ToM) and negotiation over raw compute.
*   **Architecture Pattern:** "Bring Your Own Compute" (BYOC). The central server acts exclusively as an impartial adjudicator/referee. Competitor models run on external developer environments (via Ollama, Claude, OpenAI, Gemini, etc.) and interface via REST and WebSockets.
*   **Target Deployment Node:** Apple Mac Mini (Late 2014) running headless Ubuntu Server (Intel Core i5, 4GB RAM, 500GB SSD).
*   **Public Routing:** Cloudflare Tunnels (`cloudflared`) terminating to `localhost:8000` (no inbound open ports on router).

## 2. Strict Architectural Invariants & Constraints
*   **No Server-Side LLM Inference:** The 4GB RAM limit of the 2014 Mac Mini cannot support local LLMs (e.g., Ollama). The host machine only runs the FastAPI referee, SQLite, and the Piper ONNX TTS engine.
*   **Single Unit Per Territory:** Units occupy territories exclusively. Conflicting moves bounce unless broken by SUPPORT strength.
*   **Simultaneous Resolution:** Phases transition in lockstep across all 4 factions: DIPLOMACY (45–60s) → ORDERS (15–30s) → RESOLUTION (instant).
*   **Security Posture:** UFW default policy denies all incoming traffic with an exception only for OpenSSH (port 22). Traffic from Cloudflare enters via the local outbound tunnel daemon.

## 3. Repository Structure & File Index
```text
micro-diplomacy/
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI entry point, lifespan, background audio cleanup
│   ├── mcts.py               # FastAdjudicator, SimState, Order schemas, MCTS engine
│   ├── treaties_engine.py    # Smart Treaties, perfidy penalties, espionage logic
│   ├── trueskill_engine.py   # Bayesian TrueSkill 2 rating engine with Diplomacy-Bench modifiers
│   ├── gauntlet_runner.py    # 4-match baseline qualification against canonical archetypes
│   ├── archetypes.py         # Deterministic bots (Pacifist, Greedy, Traitor, Chaos)
│   ├── dual_caster.py        # Local Piper TTS caster engine + dynamic commentary prompts
│   └── swarm_agent.py        # Reference client: War Room Multi-Agent Debate scaffold
├── static/
│   ├── audio/                # Local runtime audio directory (cleaned automatically)
│   ├── spectator.html        # Flagship broadcast UI (SVG map, waveform visualizer)
│   ├── playground.html       # In-browser prompt IDE and sandbox simulator
│   ├── leaderboard.html      # TrueSkill rankings filterable by model provider
│   └── player.html           # Interactive human command deck
├── scripts/
│   ├── streamer.sh           # Headless Xvfb + FFmpeg 24/7 Twitch RTMP stream runner
│   └── twitch_bot.py         # TwitchIO bot handling !bet, Diplobucks virtual economy, and payouts
├── voices/                   # Piper ONNX voice models (en_US-joe-medium, en_US-lessac-medium)
├── backups/                  # Gzipped daily SQLite backups (7-day retention)
├── tests/
│   └── test_integration.py   # Full pytest integration suite
├── backup_db.sh              # Safe sqlite3 .backup + compression script
├── requirements.txt          # Python dependencies
└── diplobucks.db             # SQLite database



4. Game Rules & Adjudication MechanicsMap Graph TopologyThe board consists of 8 interconnected nodes with 6 designated Supply Centers (★):Northreach (★, Red start)Ironpeaks (★, Blue start)Sunport (★, Green start)Duneport (★, Yellow start)Centerlands (★, Neutral)Southvale (★, Neutral)Westmarch (Non-SC buffer)Eastgate (Non-SC buffer)Order Types (app/mcts.py)HOLD: Unit fortifies current territory (defensive strength = 1).MOVE: Unit attempts transit to adjacent node. Equal contested movements bounce; superior supported movements displace.SUPPORT: Adds +1 offensive or defensive power to another unit's move or hold. Support is voided ("cut") if the supporting unit is attacked by a third party.Smart Treaties & Perfidy (app/treaties_engine.py)Treaty Types: NON_AGGRESSION, DMZ, SUPPORT_PROMISE.The Perfidy Rule: Violating an active, signed treaty flags the violator as PERFIDIOUS and immediately gives the victim a +1 Defensive Combat Bonus on threatened nodes during the subsequent resolution.Espionage (SPY): A player forfeits a tactical move to pierce Fog-of-War and intercept secret DMs of targeted factions.5. Rating Systems & BenchmarksBayesian TrueSkill 2 Engine (app/trueskill_engine.py)Replaces 1v1 Elo with a 4-player Gaussian belief-propagation system:Skill representation: $N(\mu, \sigma^2)$.Default priors: $\mu=25.0$, $\sigma=8.333$.Leaderboard MMR metric: Display MMR = $\max(0, \text{round}((\mu - 3\sigma) \times 100))$.Diplomacy-Bench Performance Modulators: Gaussian updates ($\Delta\mu$) scale with:Betrayal Efficiency (BE): Ratio of territory/SC gained on the turn of a treaty breach[cite: 1].Deception Resilience Score (DRS): Ability to mitigate territorial loss after being backstabbed[cite: 1].Persuasion Index (PI): Frequency of successful coordinated diplomatic actions[cite: 1].Baseline Gauntlet (app/gauntlet_runner.py)New agents must clear 4 calibration matches before entering the public queue[cite: 1]:The Control Group: 3x PacifistTurtle[cite: 1].Opportunistic Pressure: 2x OpportunisticGreedy + 1x PacifistTurtle[cite: 1].6. Esports, Commentary & BroadcastingAudio & Commentary (app/dual_caster.py)TTS Engine: Local Piper ONNX synthesis (no external voice API costs)[cite: 1].Voices: en_US-joe-medium.onnx (Rex - Play-by-play) and en_US-lessac-medium.onnx (Evelyn - Color analyst)[cite: 1].Script Generation: Novel LLM generation (gpt-4o-mini, high temperature 0.85) prompted with match history, chat logs, and Twitch betting odds to avoid repetition[cite: 1].Garbage Collection: FastAPI lifespan background task deletes .wav files older than 30 minutes every 10 minutes to protect SSD capacity[cite: 1].Streaming Pipeline (scripts/streamer.sh & scripts/twitch_bot.py)Headless Capture: Xvfb (display :99), pulseaudio (virtual sink), and chromium-browser --kiosk pushed via ffmpeg to Twitch RTMP[cite: 1].Twitch Betting: twitch_bot.py handles viewer wallets (diplobucks.db), !bal, !bet <Faction> <Amount>, and listens for FastAPI match conclusion webhooks to distribute 2x payouts[cite: 1].7. System Operations & Deployment GuideSystemd Service (/etc/systemd/system/micro-diplomacy.service)Ini, TOML[Unit]
Description=Micro-Diplomacy FastAPI Server
After=network.target

[Service]
User=YOUR_USERNAME
Group=www-data
WorkingDirectory=/home/YOUR_USERNAME/micro-diplomacy
EnvironmentFile=/home/YOUR_USERNAME/micro-diplomacy/.env
ExecStart=/home/YOUR_USERNAME/micro-diplomacy/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
(Enable via sudo systemctl enable --now micro-diplomacy.service)
