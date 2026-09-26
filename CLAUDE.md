# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Micro-Diplomacy is a "Bring Your Own Compute" AI benchmark/esports arena: a FastAPI referee server adjudicates a 4-faction, simultaneous-resolution Diplomacy-style board game, while competing LLM agents run externally (via OpenAI/Ollama/etc.) and interact over REST. The server never runs inference itself - target deployment is a 4GB-RAM Mac Mini, so all adjudication, TrueSkill/Elo rating, treaty logic, and TTS commentary must stay cheap (no local LLM calls on the server).

Full domain background (map topology, phase timing, rating formulas, deployment/systemd/UFW/Cloudflare setup) is written up in `PROJECT_HANDOFF.md` - read it for game-design rationale before changing adjudication or rating logic.

## Setup & Commands

No virtualenv exists yet and `requirements.txt` is incomplete for local dev (missing `pytest`, `pytest-asyncio`, `pytest-mock`, and - if touching `twitch_bot.py` - `twitchio`/`aiosqlite`). Install as needed:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-mock   # not pinned anywhere; needed to run tests/
```

Run the referee server (the modular package under `app/`):
```bash
uvicorn app.main:app --reload --port 8000
```

Run tests:
```bash
pytest tests/ -v
```
Note: `tests/test_integration.py` imports `FastAdjudicator`, `SimState`, and `WIN_SC_THRESHOLD` from `app.mcts`, but `app/mcts.py` currently only defines `Adjudicator` (no `FastAdjudicator`/`SimState`/`WIN_SC_THRESHOLD`). The test suite and `app/gauntlet_runner.py` / `app/gauntlet_router.py` (which import the same missing names) will fail with `ImportError` until this is reconciled - check this first if tests won't collect.

Run a reference LLM agent against a live game:
```bash
python agent.py --game-id game_1001 --faction Red --api-key sk-...
```

## Architecture

### `app/mcts.py` is the sole game-rules implementation

The map/adjudication logic (map adjacency, supply centers, order types, adjudication/dislodgement logic) used to be duplicated three ways; `app/mcts.py`'s `Adjudicator` (used by `app/main.py`, the only server this project actually runs) is now the single canonical copy:

- `engine.py` (repo root) - a standalone single-file FastAPI+WebSocket server with its own copy of the same logic - was **deleted**. It was unimported/unused anywhere in the repo, and its game logic was a strict subset of `app/mcts.py`'s (missing treaties, espionage, practice mode, real matchmaking, persistence, generated maps). It did have one real capability `app/main.py` doesn't - a WebSocket push transport for live updates - but nothing in the repo ever consumed it (no client opened a WebSocket); if real-time push delivery is wanted later, build it fresh against `app/main.py` rather than resurrecting this file.
- `agent.py` (repo root, a standalone reference OpenAI-based competitor client) no longer hardcodes the map as static prompt text - `format_map_block()` builds it fresh from a live `GET .../state` response's `adjacency`/`supply_centers` fields every phase handler call, so it can't drift out of sync with the server and correctly describes a generated-map game too, not just the classic one.
- `app/swarm_agent.py` (`WarRoomSwarm`, a second reference client) never hardcoded the map - it always passed the server's raw state dict straight into its prompts.

A fix to map topology/order semantics/adjudication rules now only needs to land in `app/mcts.py` - nothing else duplicates it.

### `app/main.py` is a minimal core; most `app/` modules are unwired subsystems

`app/main.py` only imports from `app/mcts.py` and holds all game state in an in-memory `Dict[str, GameSession]` (no persistence - despite `docker-compose.yml` provisioning a Postgres `db` service and `PROJECT_HANDOFF.md` describing a SQLite `diplobucks.db`, neither is wired into `app/main.py`). It does not mount `static/` as `StaticFiles`, and does not `include_router()` any of the following, which exist as standalone modules but aren't yet connected to the running app:

- `app/gauntlet_router.py` / `app/gauntlet_runner.py` - baseline qualification harness (4 calibration matches vs. `app/archetypes.py` bots), currently broken per the `ImportError` noted above.
- `app/server_hub.py` - agent registration, matchmaking queue, rate limiting, turn-timeout handling.
- `app/dual_caster.py` - LLM-generated two-host esports commentary script, feeding Piper TTS.
- `app/map_generator.py` - Delaunay-triangulation procedural map generator (produces topologies compatible with the fixed 8-node/6-SC layout used elsewhere).
- `app/intel_matrix.py` - fog-of-war belief-state/credibility tracking for espionage and scouting reports.

When wiring one of these into `main.py`, check its current standalone tests/demos first - several were written and tested in isolation, not against `GameSession`.

### Core game model (app/mcts.py, the canonical package copy)

- 4 factions (Red/Blue/Green/Yellow) on an 8-node graph (`ADJACENCY`), 6 of which are Supply Centers (`SUPPLY_CENTERS`). Win at 5 SCs, or most SCs at Turn 10.
- Phases: `DIPLOMACY` → `ORDERS` → resolve (simultaneous), driven by `GameSession.step_phase()` / `resolve_turn()` in `app/main.py` and a per-game `asyncio` background task (`game_loop`).
- Orders: `HOLD` / `MOVE` / `SUPPORT`, resolved by `Adjudicator.adjudicate()` - handles support cutting, head-to-head bounces, and dislodgement by comparing attack/defense strengths.
- `app/treaties_engine.py` layers on top: signed treaties (`NON_AGGRESSION`/`DMZ`/`SUPPORT_PROMISE`) checked against submitted orders each turn; a breach flags the violator `PERFIDIOUS` and grants the victim a `+1` defensive buff (this buff is computed by `TreatyAndEspionageEngine` but is not currently read by `Adjudicator.adjudicate()` - see the test in `tests/test_integration.py::test_master_e2e_betrayal_pipeline`, which asserts around this gap rather than the buff actually changing combat resolution).
- Authentication is now a real per-agent API key (`app/server_hub.py`, wired into `app/main.py` as of the auth migration - see `TODO.md`): `POST /api/v1/agents/register` issues an `api_key`; `POST /api/v1/queue/join` + polling `GET /api/v1/queue/status` gets you matched into a `game_id` with an assigned faction (both decided by the matchmaker, not the caller). `get_authorized_faction()` in `app/main.py` validates the API key *and* that the caller is actually matched into the `game_id` in the URL before allowing `POST .../messages`/`.../orders`. `POST /api/v1/games` (direct, unauthenticated creation) still exists for admin/testing/spectating, but nothing can act in a game created that way, since no agent is matched into it.

### Rating system

`app/trueskill_engine.py` is the sole rating engine - Gaussian belief-propagation (TrueSkill 2 style), `μ=25.0, σ=8.333` priors, MMR = `max(0, round((μ - 3σ) × 100))`, consuming the "Diplomacy-Bench modulators" (persuasion index, betrayal efficiency, deception resilience) as multipliers on top of the base algorithm. Used by `app/gauntlet_runner.py`, `tests/test_integration.py`, and (as of the leaderboard work below) `app/main.py` itself. (A second, independent implementation, `app/elo_calibrator.py`'s pairwise round-robin Elo, was deleted - it was standalone and unconsumed anywhere in the repo.)

**The leaderboard is now real.** `app/main.py::rate_finished_game()` is called from `game_loop()` whenever a real 4-agent match (never a practice match - `GameSession.bot_factions` is the signal) transitions to `FINISHED`: it ranks factions by final SC count, feeds neutral constants for the bench modulators (no real per-match behavioral scoring is derived from gameplay yet - a known simplification), calls `BayesianMMREngine.update_match_ratings()`, and persists each agent's updated `mu`/`sigma`/`conservative_mmr`/`wins`/`matches_played`. `GET /api/v1/leaderboard` (public, no auth) serves it, sorted by `conservative_mmr`; `static/leaderboard.html` fetches it for real instead of mock data. `AgentRecord.elo_rating` (dead, hardcoded `1200.0`) is gone, replaced by real `mu`/`sigma`/`conservative_mmr`/`wins` fields.

This also required persisting agent registration and match assignments (`app/server_hub.py`'s `agents_db`/`agent_id_lookup`/`assigned_matches` were plain in-memory dicts before - two new SQLite tables in `app/db.py`, restored in `lifespan()`), since a rating is meaningless if it evaporates on every restart. That incidentally fixed a latent bug: a restart used to leave every real agent 403'd out of its own already-resumed game.

One real, disclosed limitation worth knowing before touching this again: `BayesianMMREngine`'s adjacent-pairwise algorithm has no representation for a *tied* placement (e.g. two factions finishing with equal SCs) - `wins`/`win_rate` correctly credit every tied agent, but the underlying `mu`/`sigma` adjustment still treats them as a strict, arbitrary-among-equals ladder. See `TODO.md` for the full writeup.

### Broadcast/streaming pipeline (root-level, outside `app/`)

`streamer.sh` (Xvfb + PulseAudio + headless Chromium + FFmpeg → Twitch RTMP) captures `static/spectator.html`, and `twitch_bot.py` (TwitchIO + `aiosqlite`) runs the `!bet`/Diplobucks virtual-economy chat bot against its own `diplobucks.db`, independent of the FastAPI game server's process. `app/dual_caster.py` generates the commentary script this pipeline voices via Piper ONNX (`voices/`, currently empty - models are fetched at deploy time, not vendored).

### Static frontends (`static/*.html`)

Plain HTML/JS pages, root-mounted and served by `app/main.py` (`app.mount("/", StaticFiles(directory="static", html=True))`): `index.html` (landing page), `player.html` (human command deck, fully wired to the real API), `leaderboard.html` (real data via `GET /api/v1/leaderboard`), `docs.html`/`RULES.md`/`API.md` (rendered API/rules docs), `playground.html` (prompt IDE/sandbox, mock data, no live API calls), `spectator.html` and `caster_widget.html` (broadcast/commentary widget previews, not wired to a live game).

## Known gaps to be aware of

- `requirements.txt` doesn't include test deps (`pytest`, `pytest-asyncio`, `pytest-mock`) or `twitch_bot.py`'s deps (`twitchio`, `aiosqlite`).
- `docker-compose.yml` references `build: .` and `dockerfile: Dockerfile.worker`, but no `Dockerfile` or `Dockerfile.worker` exist in the repo yet.
- Not currently a git repository - no version history to check via `git log`/`git blame`.
