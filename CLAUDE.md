# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Micro-Diplomacy is a "Bring Your Own Compute" AI benchmark/esports arena: a FastAPI referee server adjudicates a 4-faction, simultaneous-resolution Diplomacy-style board game, while competing LLM agents run externally (via OpenAI/Ollama/etc.) and interact over REST. The server never runs inference itself — target deployment is a 4GB-RAM Mac Mini, so all adjudication, TrueSkill/Elo rating, treaty logic, and TTS commentary must stay cheap (no local LLM calls on the server).

Full domain background (map topology, phase timing, rating formulas, deployment/systemd/UFW/Cloudflare setup) is written up in `PROJECT_HANDOFF.md` — read it for game-design rationale before changing adjudication or rating logic.

## Setup & Commands

No virtualenv exists yet and `requirements.txt` is incomplete for local dev (missing `pytest`, `pytest-asyncio`, `pytest-mock`, and — if touching `twitch_bot.py` — `twitchio`/`aiosqlite`). Install as needed:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-mock   # not pinned anywhere; needed to run tests/
```

Run the referee server (the modular package under `app/`):
```bash
uvicorn app.main:app --reload --port 8000
```

Run the standalone alternate server (see "Two parallel implementations" below):
```bash
uvicorn engine:app --reload --port 8000
```

Run tests:
```bash
pytest tests/ -v
```
Note: `tests/test_integration.py` imports `FastAdjudicator`, `SimState`, and `WIN_SC_THRESHOLD` from `app.mcts`, but `app/mcts.py` currently only defines `Adjudicator` (no `FastAdjudicator`/`SimState`/`WIN_SC_THRESHOLD`). The test suite and `app/gauntlet_runner.py` / `app/gauntlet_router.py` (which import the same missing names) will fail with `ImportError` until this is reconciled — check this first if tests won't collect.

Run a reference LLM agent against a live game:
```bash
python agent.py --game-id game_1001 --faction Red --api-key sk-...
```

## Architecture

### Two parallel, non-interoperating implementations

The game rules (map adjacency, supply centers, order types, adjudication/dislodgement logic) are implemented **independently in three places** and are not shared code:

- `app/mcts.py` — `Adjudicator`, used by `app/main.py` (the package entrypoint, `uvicorn app.main:app`).
- `engine.py` (repo root) — a self-contained single-file FastAPI+WebSocket server with its own copy of the map/adjudication logic. Runs standalone via `uvicorn engine:app`, independent of `app/`.
- `agent.py` (repo root) — a standalone reference OpenAI-based competitor client with the map/rules baked into its system prompt string, separate from `app/swarm_agent.py`'s `WarRoomSwarm` reference client.

If you change map topology, order semantics, or adjudication rules, decide which of these you're targeting — a fix in `app/mcts.py` will not propagate to `engine.py` or `agent.py`'s prompt text.

### `app/main.py` is a minimal core; most `app/` modules are unwired subsystems

`app/main.py` only imports from `app/mcts.py` and holds all game state in an in-memory `Dict[str, GameSession]` (no persistence — despite `docker-compose.yml` provisioning a Postgres `db` service and `PROJECT_HANDOFF.md` describing a SQLite `diplobucks.db`, neither is wired into `app/main.py`). It does not mount `static/` as `StaticFiles`, and does not `include_router()` any of the following, which exist as standalone modules but aren't yet connected to the running app:

- `app/gauntlet_router.py` / `app/gauntlet_runner.py` — baseline qualification harness (4 calibration matches vs. `app/archetypes.py` bots), currently broken per the `ImportError` noted above.
- `app/server_hub.py` — agent registration, matchmaking queue, rate limiting, turn-timeout handling.
- `app/dual_caster.py` — LLM-generated two-host esports commentary script, feeding Piper TTS.
- `app/map_generator.py` — Delaunay-triangulation procedural map generator (produces topologies compatible with the fixed 8-node/6-SC layout used elsewhere).
- `app/intel_matrix.py` — fog-of-war belief-state/credibility tracking for espionage and scouting reports.
- `app/elo_calibrator.py` — a second, separate rating system (`WeightedEloCalibrator`) alongside `app/trueskill_engine.py`'s Bayesian TrueSkill 2 engine; not imported anywhere else (has its own `if __name__ == "__main__"` demo).

When wiring one of these into `main.py`, check its current standalone tests/demos first — several were written and tested in isolation, not against `GameSession`.

### Core game model (app/mcts.py, the canonical package copy)

- 4 factions (Red/Blue/Green/Yellow) on an 8-node graph (`ADJACENCY`), 6 of which are Supply Centers (`SUPPLY_CENTERS`). Win at 5 SCs, or most SCs at Turn 10.
- Phases: `DIPLOMACY` → `ORDERS` → resolve (simultaneous), driven by `GameSession.step_phase()` / `resolve_turn()` in `app/main.py` and a per-game `asyncio` background task (`game_loop`).
- Orders: `HOLD` / `MOVE` / `SUPPORT`, resolved by `Adjudicator.adjudicate()` — handles support cutting, head-to-head bounces, and dislodgement by comparing attack/defense strengths.
- `app/treaties_engine.py` layers on top: signed treaties (`NON_AGGRESSION`/`DMZ`/`SUPPORT_PROMISE`) checked against submitted orders each turn; a breach flags the violator `PERFIDIOUS` and grants the victim a `+1` defensive buff (this buff is computed by `TreatyAndEspionageEngine` but is not currently read by `Adjudicator.adjudicate()` — see the test in `tests/test_integration.py::test_master_e2e_betrayal_pipeline`, which asserts around this gap rather than the buff actually changing combat resolution).
- Authentication is now a real per-agent API key (`app/server_hub.py`, wired into `app/main.py` as of the auth migration — see `TODO.md`): `POST /api/v1/agents/register` issues an `api_key`; `POST /api/v1/queue/join` + polling `GET /api/v1/queue/status` gets you matched into a `game_id` with an assigned faction (both decided by the matchmaker, not the caller). `get_authorized_faction()` in `app/main.py` validates the API key *and* that the caller is actually matched into the `game_id` in the URL before allowing `POST .../messages`/`.../orders`. `POST /api/v1/games` (direct, unauthenticated creation) still exists for admin/testing/spectating, but nothing can act in a game created that way, since no agent is matched into it.

### Rating systems

Two independent 4-player rating engines exist, both consuming the same "Diplomacy-Bench modulators" (persuasion index, betrayal efficiency, deception resilience) as multipliers on top of a base algorithm:
- `app/trueskill_engine.py` — Gaussian belief-propagation (TrueSkill 2 style), `μ=25.0, σ=8.333` priors, MMR = `max(0, round((μ - 3σ) × 100))`. Used by `app/gauntlet_runner.py`.
- `app/elo_calibrator.py` — pairwise round-robin Elo with zero-sum drift correction. Standalone, not currently consumed elsewhere.

### Broadcast/streaming pipeline (root-level, outside `app/`)

`streamer.sh` (Xvfb + PulseAudio + headless Chromium + FFmpeg → Twitch RTMP) captures `static/spectator.html`, and `twitch_bot.py` (TwitchIO + `aiosqlite`) runs the `!bet`/Diplobucks virtual-economy chat bot against its own `diplobucks.db`, independent of the FastAPI game server's process. `app/dual_caster.py` generates the commentary script this pipeline voices via Piper ONNX (`voices/`, currently empty — models are fetched at deploy time, not vendored).

### Static frontends (`static/*.html`)

Plain HTML/JS pages, not currently served by `app/main.py` (no `StaticFiles` mount): `spectator.html` (broadcast/SVG map UI), `playground.html` (prompt IDE/sandbox), `leaderboard.html`, `player.html` (human command deck), `caster_widget.html`. `static/docs.html)` has a stray trailing `)` in its filename — likely a typo, worth fixing if you touch it.

## Known gaps to be aware of

- `requirements.txt` doesn't include test deps (`pytest`, `pytest-asyncio`, `pytest-mock`) or `twitch_bot.py`'s deps (`twitchio`, `aiosqlite`).
- `docker-compose.yml` references `build: .` and `dockerfile: Dockerfile.worker`, but no `Dockerfile` or `Dockerfile.worker` exist in the repo yet.
- Not currently a git repository — no version history to check via `git log`/`git blame`.
