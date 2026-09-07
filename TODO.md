# TODO: Known gaps and required fixes

Task list derived from a full read-through of the codebase (see `CLAUDE.md` for
the architecture summary these reference). Grouped by priority; items note
blocking dependencies where they exist.

## Blocking / breaks the codebase today

- [x] **Fix the `app.mcts` import mismatch that breaks the test suite and the
      gauntlet subsystem.** *(Done — `pytest tests/` is 5/5 green via
      `python -m pytest tests/` in a `venv` with `requirements.txt` +
      `pytest pytest-asyncio pytest-mock` installed.)*
      Went with option 1 from the original plan: added `SimState` (`turn`,
      `map_units: Dict[str,str]`, `map_sc: Dict[str,str]`, `is_terminal()`,
      `get_scores()`), `WIN_SC_THRESHOLD = 5`, and
      `FastAdjudicator.step(state, joint_orders) -> SimState` to
      `app/mcts.py`, delegating to the existing `Adjudicator.adjudicate()`.
      Fixing the import chain end-to-end surfaced several more bugs that were
      previously masked by the collection-level `ImportError` — all fixed:
      - `app/gauntlet_runner.py`: missing `Optional` import (separate
        `NameError` on `GauntletHarness.__init__`'s type hint); its
        `MatchResultSnapshot` construction used `agent_id="Red"` for the
        candidate instead of `candidate_agent_id`, causing a `KeyError` in
        `BayesianMMREngine.update_match_ratings` since the candidate is only
        ever registered under its own `agent_id`.
      - `app/archetypes.py`: `generate_orders()`/`generate_messages()`
        expected a `Dict[str, TerritoryState]`-shaped `map_state`
        (`owner.get("unit_faction")` etc.), but `gauntlet_runner.py` was
        always passing the flat `state.map_units`. Switched all four
        archetypes to take the `SimState` directly. Also fixed
        `random.choice()` being called on `ADJACENCY.get(u, [])`, which
        returns a `Set[str]` (not subscriptable) — wrapped in `list(...)`.
      - `app/trueskill_engine.py`: missing `Any` import, same class of bug as
        `gauntlet_runner.py`'s (ran a static AST check across all of `app/*.py`
        and root `*.py` afterward — no further instances of this pattern).
      - `app/swarm_agent.py`: `WarRoomSwarm.__init__` eagerly constructed an
        `AsyncOpenAI` client and raised immediately if `OPENAI_API_KEY` wasn't
        set — masked before because the test file never got past collection.
        Now falls back to a placeholder key at construction time (so
        credential errors surface at the first real API call, not
        construction) and accepts an optional `openai_client` for injection.
      - `tests/test_integration.py`: `test_master_e2e_betrayal_pipeline`'s
        `mock_post(url, json)` stub didn't accept the `headers` kwarg that
        `execute_debate_cycle()` actually passes to `arena.post()` — added
        `**kwargs`.
      - Note for next time: plain `pytest tests/` fails with
        `ModuleNotFoundError: No module named 'app'` because there's no
        `conftest.py`/`pytest.ini` anchoring rootdir on `sys.path` — use
        `python -m pytest tests/` (adds cwd to `sys.path`), or add a root
        `conftest.py`/`pyproject.toml` pytest config as a follow-up.

## Persistence & deployment

- [x] **Decide on and implement a real persistence layer.** *(Done — verified
      live: created a game, sent a message, hard-killed the `uvicorn`
      process, started a fresh one against the same DB file, and confirmed
      both the game state and the message were still there and the game's
      countdown timer resumed ticking.)*
      Decision: **SQLite via SQLAlchemy async + `aiosqlite`**, not Postgres —
      `docker-compose.yml`'s Postgres provisioning directly contradicted
      `PROJECT_HANDOFF.md`'s actual deployment story (systemd + bare Ubuntu on
      a 4GB-RAM Mac Mini, no separate DB server) and `backup_db.sh` (already
      SQLite-based), and the project's stated architecture principle is no
      heavy server-side services. Implementation:
      - `app/db.py` (new): a single `games` table storing each `GameSession`
        as one JSON document keyed by `game_id` (not a normalized relational
        schema — the state is small, short-lived, and already modeled as
        nested pydantic objects, so a document-per-game store was the
        simplest thing that actually works). `init_db()`, `save_game_state()`,
        `load_all_game_states()`. Defaults to `sqlite+aiosqlite:///./diplomacy.db`,
        overridable via `DATABASE_URL`.
      - `app/main.py`: added `GameSession.to_state()`/`.restore()` for
        serialization; a `lifespan` handler that calls `init_db()` and reloads
        any not-yet-`FINISHED` games from disk on startup, re-spawning their
        `game_loop` background task via `asyncio.create_task` (they were
        previously only ever started via `BackgroundTasks` from the
        `create_game` request, so a reloaded game's timer wouldn't have
        resumed without this); `create_game`/`send_message`/`submit_orders`
        and the per-tick `game_loop` now `await save_game_state(...)` after
        every mutation. The three mutating endpoints became `async def` to
        support this (they were plain `def` before).
      - `requirements.txt`: swapped `asyncpg` for `aiosqlite>=0.20.0,<0.23.0`
        (this also happens to close the separate "twitch_bot.py needs
        aiosqlite" gap noted below, since it's the same dependency).
      - `docker-compose.yml`: removed the Postgres `db` service and its
        `DATABASE_URL`/`depends_on`/`pgdata` volume so it no longer
        contradicts the decision above. Did **not** add a volume mount for
        the SQLite file, since that depends on a `Dockerfile` `WORKDIR` that
        doesn't exist yet (see the missing-`Dockerfile` item below) — left a
        comment noting it needs finishing once that exists.
- [x] **Add the missing `Dockerfile`s or trim `docker-compose.yml`.** *(Done —
      verified live with both plain `docker build`/`docker run` and
      `docker-compose up -d --build`/`restart`: built the image, created a
      game through the containerized API, restarted the container, and
      confirmed the game state + running timer survived via the mounted
      volume, exactly like the bare-metal restart test for the persistence
      item above.)*
      Added a real `Dockerfile` for `diplomacy-engine` (`python:3.12-slim`,
      installs `requirements.txt`, copies `app/`, runs
      `uvicorn app.main:app`) and a `.dockerignore`. Did **not** write
      `Dockerfile.worker` / a tournament-worker entrypoint — it referenced a
      `VLLM_BASE_URL` with no corresponding code anywhere in the repo, so
      building it would mean inventing an entire unspecified worker
      subsystem rather than fixing a broken reference. Removed the
      `tournament-worker` service from `docker-compose.yml` instead (the
      TODO item's own suggested fallback) with a comment explaining why, to
      re-add once that subsystem actually has a design/implementation.
      Also closed the loop left open by the persistence-layer item above:
      `docker-compose.yml` now sets `DATABASE_URL=sqlite+aiosqlite:////data/diplomacy.db`
      and mounts a `diplomacy_data` named volume at `/data`, so the SQLite
      file actually survives `docker-compose restart`/recreation instead of
      living inside the container's writable layer.
- [x] **Reconcile `requirements.txt` with what's actually imported.** *(Done —
      verified from a completely fresh `venv`, not just reasoned about: base
      `requirements.txt` alone imports `app.main` fine; `twitch_bot.py`
      genuinely `ModuleNotFoundError`s on `twitchio` until
      `requirements-twitch.txt` is installed, then imports cleanly; bare
      `pytest` (no `python -m`) is not found until `requirements-dev.txt` is
      installed, then `pytest tests/` is 5/5.)*
      Split into three files rather than one, since the three consumers
      genuinely run on different machines/processes:
      - `requirements.txt` — unchanged core FastAPI referee deps (what the
        `Dockerfile` installs).
      - `requirements-dev.txt` — adds `pytest`, `pytest-asyncio`,
        `pytest-mock` (`-r requirements.txt` + test tooling only).
      - `requirements-twitch.txt` — adds `twitchio` for `twitch_bot.py`,
        a separate process from the core referee per `PROJECT_HANDOFF.md`.
        **Pinned to the 2.x line deliberately** (`twitchio>=2.8.0,<3.0.0`):
        installing latest (3.3.2) first and actually importing `twitch_bot.py`
        against it raised `TypeError: Bot.__init__() missing 1 required
        keyword-only argument: 'client_id'` — twitchio 3.x is a breaking
        rewrite of the auth/bot API that `twitch_bot.py`'s
        `commands.Bot(token=..., prefix=..., initial_channels=...)` call
        was never written against. Reinstalling 2.10.0 imports cleanly.
        Naively pinning "whatever's latest" would have reconciled the
        dependency list on paper while shipping code that crashes on import.
      Also added a root `conftest.py` (empty, just anchors pytest's rootdir)
      so plain `pytest tests/` now works without needing `python -m pytest`
      or a `PYTHONPATH` override.
- [ ] **`git init` the repo.** There's currently no version history, which
      makes every fix above harder to review/revert incrementally. Do this
      before starting on the larger items so changes are tracked.

## Wiring the disconnected subsystems into `app/main.py`

None of these are `include_router()`'d or otherwise called from
`app/main.py` today. Each was written/tested standalone, so wiring it in is
more than adding an import:

- [ ] **`app/gauntlet_router.py` / `app/gauntlet_runner.py`** — blocked on the
      import-mismatch fix above. Once unblocked, mount the router in
      `app/main.py` and decide how a real candidate agent (not the router's
      current `mock_agent_policy` stub) submits its order function for
      calibration.
- [ ] **Mount `static/` as `StaticFiles`.** `app/main.py` never serves
      `static/`, so `spectator.html`, `leaderboard.html`, `player.html`,
      `playground.html`, and `caster_widget.html` are unreachable through the
      running server even though `streamer.sh` hard-codes
      `http://localhost:8000/spectator.html`. Add
      `app.mount("/", StaticFiles(directory="static", html=True), name="static")`
      (or under a `/static` prefix — pick one and make sure `streamer.sh`'s
      URL matches it).
- [ ] **Rename `static/docs.html)`** (stray trailing `)` in the filename) to
      `static/docs.html`. No current references were found to the broken
      name, but re-check once `static/` is actually mounted and linked from
      other pages.
- [ ] **`app/server_hub.py` vs. `app/main.py` auth.** `app/main.py`'s
      `authenticate_agent()` treats the raw `Bearer` token as the faction name
      (`Red`/`Blue`/`Green`/`Yellow`) with no real secret — anyone who knows
      the faction name can act as that faction. `server_hub.py` already has a
      proper per-agent `AgentRecord`/API-key/rate-limiter implementation that
      isn't used anywhere. Decide whether to migrate `app/main.py` onto
      `server_hub`'s registration + auth flow (recommended before any public
      deployment) and, if so, update `agent.py` and `app/swarm_agent.py`'s
      client-side `Authorization` headers to match.
- [ ] **`app/dual_caster.py`.** Nothing currently calls
      `DualShoutcasterService`. Needs: an `OPENAI_API_KEY` env var at
      runtime, and a call site in `app/main.py`'s `resolve_turn()` (or a
      background task) that feeds it that turn's combat events / treaty
      breach events and broadcasts the resulting script to spectators (no
      delivery mechanism — e.g. WebSocket push to `spectator.html` — exists
      yet either). Also has the same eager-`AsyncOpenAI()`-construction issue
      that `app/swarm_agent.py`'s `WarRoomSwarm` had before it was fixed
      above (`DualShoutcasterService.__init__` raises immediately if
      `OPENAI_API_KEY` is unset) — apply the same placeholder-key fix when
      wiring this in, so tests/dev environments without a key don't crash at
      construction.
- [ ] **`app/map_generator.py`.** `MapGenerator.generate_topology()` produces
      a randomized Delaunay planar graph, but `ADJACENCY`, `SUPPLY_CENTERS`,
      and `STARTING_POSITIONS` in `app/mcts.py` are hardcoded module-level
      constants that `Adjudicator` and `GameSession` both close over directly.
      Using generated maps requires refactoring those from module constants
      to per-`GameSession` instance state first — a real (if small)
      architectural change, not just calling the generator.
- [ ] **`app/intel_matrix.py`.** `IntelligenceVerificationMatrix` needs a
      per-faction "line of sight" set to do anything
      (`synthesize_belief_state()` / `audit_ground_truth()` both take one as
      a parameter), but no line-of-sight concept exists anywhere in the
      current map/game model — it would need to be defined (e.g. adjacent
      territories to owned units) before this module can be wired in.

## Gameplay logic gaps

- [ ] **Make treaty breaches actually affect combat.**
      `TreatyAndEspionageEngine.evaluate_orders_for_breaches()` computes
      `defensive_buffs: Dict[faction, Dict[territory, int]]` on a breach, but
      `Adjudicator.adjudicate()` in `app/mcts.py` never reads it — a breach
      currently only sets a flag and produces a log message; the
      "PERFIDY Rule" (+1 defensive combat bonus) described in
      `PROJECT_HANDOFF.md` has no actual gameplay effect right now. Thread
      `defensive_buffs` into `Adjudicator.adjudicate()`'s hold-strength
      calculation (~`app/mcts.py:141`), and call
      `TreatyAndEspionageEngine.evaluate_orders_for_breaches()` from
      `GameSession.resolve_turn()` in `app/main.py` before adjudication runs
      each turn. `tests/test_integration.py::test_master_e2e_betrayal_pipeline`
      currently asserts around this gap rather than exercising it — it should
      start asserting the buff changed the actual combat outcome once fixed.

## Consolidation (multiple implementations of the same thing)

- [ ] **Decide the canonical game-rules implementation and archive/delete the
      others, or generate them from one source.** Map topology + adjudication
      logic currently exists independently in `app/mcts.py` (used by
      `app/main.py`), root `engine.py` (a separate standalone
      FastAPI+WebSocket server, `uvicorn engine:app`), and root `agent.py`
      (rules restated as prose inside its system-prompt string). `app/mcts.py`
      is the one the tests and gauntlet target, so it's the de facto
      canonical copy. Either delete/archive `engine.py`, or clearly mark it as
      an experimental alternate implementation so future rule changes don't
      silently only land in one of the three.
- [ ] **Decide the canonical rating system.** `app/trueskill_engine.py` (used
      by `app/gauntlet_runner.py`) and `app/elo_calibrator.py` (standalone,
      only exercised by its own `if __name__ == "__main__"` demo) are two
      independent implementations of the same Diplomacy-Bench-weighted rating
      idea. Pick one as canonical for the public leaderboard, or explicitly
      wire the other in as a secondary/alternate rating and document why both
      exist.
- [ ] **Reconcile `PROJECT_HANDOFF.md`'s file index with actual layout.**
      It documents `scripts/streamer.sh` and `scripts/twitch_bot.py`, but
      both files actually live at the repo root (`scripts/` is empty). Either
      move the two files into `scripts/` to match the doc, or fix the doc to
      reflect root placement — don't leave them contradicting each other.
- [ ] **Fetch the Piper voice models before relying on the caster/stream
      pipeline.** `voices/` is currently empty; `instruct.ions` step 4
      describes fetching `en_US-joe-medium` and `en_US-lessac-medium` `.onnx`
      models via `wget`, which is required before `app/dual_caster.py` or
      `streamer.sh`'s audio path will work end to end.
