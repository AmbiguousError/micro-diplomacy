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
- [x] **`git init` the repo.** *(Done — `git log --oneline` shows one commit
      on `main`, `git status` is clean.)*
      Added `.gitignore` (`venv/`, `__pycache__/`, `.pytest_cache/`, `*.db`,
      `static/audio/`) before staging anything, then reviewed `git status`
      after `git add -A` to confirm nothing unwanted (venv, db files, caches)
      was included and nothing secret-looking was in the diff before
      committing. Note: no git author identity was configured on this
      machine — set `user.name`/`user.email` locally (`--local`, this repo
      only, not `--global`) after checking with the user for what to use,
      since a global config change wasn't something to make unilaterally.

## Wiring the disconnected subsystems into `app/main.py`

None of these are `include_router()`'d or otherwise called from
`app/main.py` today. Each was written/tested standalone, so wiring it in is
more than adding an import:

- [x] **`app/gauntlet_router.py` / `app/gauntlet_runner.py`.** *(Done —
      verified live: wrote a tiny stub "candidate" FastAPI server exposing
      `POST /policy`, ran it alongside the real referee, hit
      `POST /api/v1/gauntlet/calibrate/TestBot_v1` with its callback URL,
      and got back a real 4-match result (`passed: true`, tier `GOLD`) in
      54ms — confirming matches really do run instantly rather than over
      real 150s/turn timers. Also verified the failure path: an unreachable
      `callback_url` correctly returns `422` with a per-turn syntax-error
      count, and the main server stays healthy afterward rather than
      crashing. Full test suite still 5/5.)*
      The design question was how a real candidate agent — whose decision
      logic runs on the candidate's own machine, per the project's
      Bring-Your-Own-Compute model — plugs into `GauntletHarness`'s
      synchronous, in-process `candidate_order_fn(turn, map_units)`
      simulation loop. Went with an HTTP callback: `POST .../calibrate/{id}`
      now takes a `callback_url` in its body, and the harness POSTs
      `{turn, map_units}` to it once per simulated turn, expecting
      `{"orders": [...]}` back (same order shape as `POST .../orders`).
      Any callback failure is caught per-turn by `gauntlet_runner.py`'s
      existing exception handling and counted as a syntax error rather than
      aborting the match — no changes needed there.
      `run_calibration_suite()` itself stays fully synchronous (it already
      was); the router's endpoint wraps it in `asyncio.to_thread(...)` so
      its blocking HTTP calls to the candidate don't block the event loop.
      Mounted via `app.include_router(gauntlet_router)` in `app/main.py`.
      Documented the full callback contract in `static/API.md`, including
      an honest caveat: there's no separate registration/matchmaking queue
      live yet (that's `app/server_hub.py`, still unwired — see below), so
      right now this is a standalone scoring tool, not something the server
      actually gates entry with.
- [x] **Mount `static/` as `StaticFiles`.** *(Done — found by the user
      trying to open the page in a real browser and getting nothing, since
      `app/main.py` had no route for it at all. Verified via curl: `/`
      correctly 404s (no `index.html`), `/spectator.html` and `/player.html`
      both 200, `/api/v1/games` still works unaffected. Not verified in an
      actual browser — the Claude-in-Chrome extension wasn't connected in
      this environment, so this needs a human check.)*
      Added `app.mount("/", StaticFiles(directory="static", html=True), name="static")`
      at the very end of `app/main.py` (after every `@app.get`/`@app.post`
      route), so it only catches paths none of the `/api/v1/...` routes
      matched. Mounted at root, not under `/static`, to match
      `player.html`'s root-relative `API_BASE = "/api/v1/games/game_1001"`
      fetches and `streamer.sh`'s hardcoded
      `http://localhost:8000/spectator.html`.
- [x] **Rename `static/docs.html)`** (stray trailing `)` in the filename) to
      `static/docs.html`. *(Done — `git mv`'d to preserve history; confirmed
      no code referenced the broken filename; test suite still 5/5.)*
      Found something more important while doing this: unlike
      `spectator.html`/`caster_widget.html`, `docs.html` **is** a complete,
      well-formed page (proper `<head>`/Tailwind) — but its content actively
      contradicts the real live API. It documents `POST
      /api/v1/agents/register` and `POST /api/v1/queue/join` (the
      `app/server_hub.py` registration/matchmaking design) and a real
      per-agent Bearer API key, none of which exist in the running server —
      the real flow is `POST /api/v1/games` directly with no registration,
      and `Authorization: Bearer <FactionName>` is the only "credential"
      (see the auth item above). It's not linked from anywhere right now
      (including the new `static/index.html` landing page — deliberately,
      for this reason), but anyone who finds `/docs.html` directly would get
      actively wrong information that conflicts with `static/RULES.md` and
      `static/API.md`. Needs a decision once `server_hub.py` is either wired
      in (in which case update it to match, or point it at the new docs) or
      confirmed out of scope (in which case delete it or clearly mark it
      "planned, not yet live") — not fixed here since it's a content/scope
      decision, not a typo fix.
- [x] **`static/spectator.html` and `static/caster_widget.html` aren't full
      HTML documents.** *(Done — the "at minimum" option from this item's
      original write-up, not the full from-scratch SVG map rebuild; see
      below for why. Verified live: both return `200` with intact content,
      full test suite still 5/5, and a tag-balance check found no unclosed
      elements in either file — real browser confirmation is still
      outstanding since the Claude-in-Chrome extension isn't connected in
      this environment.)*
      On closer inspection while fixing this, the two files aren't actually
      near-identical duplicates as first thought: `caster_widget.html` is
      the more complete one — it has a working `<script>` using the
      browser's native `SpeechSynthesis` API to genuinely speak commentary
      aloud, a transcript log, and a tension meter. `spectator.html` is a
      simpler, purely decorative variant with **no `<script>` at all**, so
      its one interactive element (`onclick="toggleDualCasterAudio()"`) was
      calling a function that didn't exist anywhere — doubly broken, not
      just missing its outer `<head>`.
      Wrapped both in a proper `<!DOCTYPE html>`/`<head>` (Tailwind CDN)
      without inventing new functionality: gave `spectator.html` a small
      local stub for the audio toggle (a canvas-only visual, honestly
      captioned as not wired to real audio) instead of duplicating
      `caster_widget.html`'s more complete implementation into it; gave
      `caster_widget.html` the `.chat-scroll` scrollbar CSS its markup
      already referenced but that only lived in `player.html`'s
      `<style>` block, so it wasn't actually applying before. Added an
      honest on-page caption to each noting it's a static preview, not
      wired to a live game or the server's real Piper TTS pipeline
      (`app/dual_caster.py`). Did **not** build the "SVG map, waveform
      visualizer" flagship spectator page `PROJECT_HANDOFF.md` describes —
      that depends on data that doesn't fully exist yet either (live map
      polling, real synthesized audio via the still-unwired
      `app/dual_caster.py`), so building it now would itself be a
      half-finished feature; a real one is a separate, larger task.
      Now that both pages are honest and working, linked them from
      `static/index.html`'s "Try It Yourself" section (as "Broadcast Desk
      Preview" / "AI Shoutcaster Preview", not implying live functionality)
      — closing the loop on this item's own note that they were
      deliberately left unlinked until fixed.
- [x] **`app/server_hub.py` vs. `app/main.py` auth.** *(Done — full
      migration, chosen explicitly over the smaller "per-game key only"
      alternative. Verified live end-to-end, not just unit-tested: a
      standalone test script registered 4 agents, joined them all to the
      queue, confirmed the matchmaker actually spun up a real `GameSession`
      (not just a `game_id` string — see below) and assigned 4 distinct
      factions, then confirmed: a real `api_key` can send a message; the
      *old* `Authorization: Bearer <FactionName>` scheme is now rejected
      (`403`, "Invalid API key."); a valid key used against a
      *different*/unmatched `game_id` is rejected (`403`, "Your agent is
      not assigned to this game."); a bogus key is rejected (`403`); a full
      real turn (waiting out the actual 120s+30s timers) was played and
      resolved end-to-end using real agent API keys for order submission.
      Full test suite still 5/5.)*
      `server_hub.py` had no HTTP routes at all before this — it was pure
      logic and data structures, never mounted. Also, its
      `matchmaker_worker()` only ever generated a `game_id` *string* and
      populated `assigned_matches`; it never actually created a
      `GameSession`, so even if it had been called, matched agents would
      have had nothing real to play against.
      - `app/server_hub.py`: added a real `APIRouter` with
        `POST /agents/register`, `POST /queue/join`, `GET /queue/status`.
        `matchmaker_worker()` now takes a `create_game_fn` callback
        (injected by `app/main.py`) so it can actually spawn a game once 4
        agents are matched, without a circular import between the two
        modules. Also swapped its locally-redefined `FACTIONS` constant for
        importing the one already in `app/mcts.py` (was a duplicate).
      - `app/main.py`: removed the old faction-name `authenticate_agent()`
        entirely, replacing it with `get_authorized_faction()` — a
        dependency that validates a real API key via
        `server_hub.authenticate_agent` *and* checks the caller's
        `assigned_matches` entry actually points at the `game_id` in the
        URL. Factored a `spawn_game()` helper out of the old
        `create_game()` endpoint body so both it and the matchmaker
        callback share the same game-creation/persistence/`game_loop`-start
        logic. `POST /api/v1/games` (direct creation) still exists,
        deliberately, for admin/testing/spectating — but games created that
        way now have no agents matched into them, so nothing can actually
        act in them via messages/orders anymore; only matchmaker-created
        games can be played.
      - `agent.py`: rewritten from `--game-id`/`--faction` CLI args (now
        meaningless — both are assigned by the matchmaker) to
        `--agent-name`/`--developer-handle`/`--model-identifier`; added
        `register_and_queue()`, called automatically by `run()`.
      - `app/swarm_agent.py`: added a `self.api_key` attribute (set
        externally, same pattern as the existing `self.my_faction`/
        `self.game_id`); its final orders `POST` now authenticates with it
        instead of `Bearer {self.my_faction}`.
      - Updated `static/API.md`, `static/index.html`, and
        `static/docs.html` to match — all three previously described (or,
        for `docs.html`, half-implied without actually working) the old
        flow. `docs.html`'s Python snippet in particular was fixed and then
        actually executed (4 concurrent copies) against the live server to
        confirm it now genuinely registers, queues, and gets matched, not
        just "looks plausible."
      Explicitly out of scope for this item (noted for later, not done
      here): `TurnTimeoutManager.resolve_submitted_or_default_orders()` and
      `AgentRecord.consecutive_timeouts` still aren't wired into
      `resolve_turn()` — timeout tracking / any future "kick after N
      misses" policy is a separate, smaller follow-up, not an auth concern.
- [x] **`app/dual_caster.py`.** *(Done — delivery mechanism chosen
      explicitly: added to the existing polled `GET .../state` response
      rather than building new WebSocket push infrastructure (the
      alternative this item originally suggested). Verified two ways: (1)
      in-process with a mocked OpenAI client — confirmed the
      `{"dialogue": [...]}` parsing fix actually works, confirmed it
      round-trips through `to_state()`/`restore()` and the `GameState`
      response model, and confirmed a simulated failure is caught without
      raising; (2) live against the real running server with no
      `OPENAI_API_KEY` set — played a real turn to resolution and confirmed
      in the server log that a genuine call was attempted, got a real `401`
      back from OpenAI, was caught cleanly, and the turn still resolved
      normally (`caster_script: []`, no crash). Full test suite still 5/5.)*
      Found a second, independent bug while reading the file closely, before
      ever calling it: the system prompt told the LLM to output a bare JSON
      array, but the parsing code did `.get("dialogue", [])` — expecting an
      *object* with a `"dialogue"` key. Combined with
      `response_format={"type": "json_object"}` (which forces the OpenAI API
      to return an object, never a bare array), the model had no way to
      know it should nest the array under `"dialogue"` — in practice this
      would have silently produced empty commentary even with a valid API
      key and a fully working call. Fixed the prompt to specify the exact
      wrapper shape the code actually parses.
      Also applied the same eager-`AsyncOpenAI()`-construction fix as
      `app/swarm_agent.py`'s `WarRoomSwarm`, and renamed the leading-
      underscore `_generate_llm_script()` to `generate_broadcast_script()`
      since it's now called from outside the class (`app/main.py`), not
      just used internally.
      Wiring: `GameSession` gained a `caster_script` field (persisted,
      restored, included in `GameState`); `game_loop()` calls
      `update_caster_script()` right after a turn actually resolves
      (distinguished from the DIPLOMACY→ORDERS phase-timer tick, which
      shouldn't trigger commentary generation) — any failure there is
      caught and clears `caster_script` to `[]` rather than propagating and
      breaking the game loop. Treaty breach events are passed through as an
      empty list for now, matching reality (treaties aren't wired into
      `resolve_turn()` yet — separate TODO item below).
      Not done, deliberately out of scope per the chosen delivery
      mechanism: no WebSocket endpoint, and `spectator.html`/
      `caster_widget.html` still don't actually fetch or display
      `caster_script` — they remain the static demos described in the item
      above this one. Wiring the display side is a natural next step but a
      separate, smaller piece of work.
- [x] **Wire `app/map_generator.py` into live games.** *(Done — verified
      with a local live server: a fixed-map practice match's
      `GET .../state` exactly matches the classic `ADJACENCY`/
      `SUPPLY_CENTERS` constants; a generated-map practice match has 8
      territories, 6 SCs, 4 distinct factions on distinct SC starting
      territories, and a real turn resolves correctly using the generated
      (not classic) adjacency — confirmed via a bot move that's only legal
      under the generated graph; a generated game's topology round-trips
      correctly through a full process restart (same method used to
      originally verify the SQLite persistence layer). Full pytest suite
      still 5/5, unchanged.)*
      Did the actual refactor this item called for: `ADJACENCY`,
      `SUPPLY_CENTERS`, `STARTING_POSITIONS` stay exactly as they were
      (nothing that reads them directly needed to change), but
      `Adjudicator.adjudicate()`, `SimState`, `FastAdjudicator.step()`, and
      `GameSession` now all take a `MapTopology` (`app/mcts.py`) — bundles
      adjacency/supply_centers/starting_positions/coordinates — as a
      parameter/instance attribute defaulting to `CLASSIC_TOPOLOGY` (built
      from the unchanged globals), so every existing call site keeps
      working with zero changes. `app/archetypes.py`'s three bot classes
      switched from importing `ADJACENCY`/`SUPPLY_CENTERS` directly to
      reading `state.topology.adjacency`/`state.topology.supply_centers`,
      so practice-match bots actually play correctly on a generated map
      instead of silently using the wrong graph.
      New `build_generated_topology()` (`app/mcts.py`) wraps
      `MapGenerator.generate_topology()`, fixing two real gaps found in
      it: its `adjacency` values are `list`s (everywhere else expects
      `Set[str]`), and it produces no starting-position assignment at all
      — `build_generated_topology()` picks 4 of its `supply_centers` for
      `FACTIONS` (the rest stay neutral, same as the classic map's
      Centerlands/Southvale).
      `POST /api/v1/games` and `POST /api/v1/practice` both gained an
      optional `?map_mode=fixed|generated` query param (default `fixed` —
      no existing caller's behavior changes). `GameState` gained
      `map_mode`/`adjacency`/`supply_centers`/`coordinates` fields so a
      client can read a game's *actual* map instead of assuming the
      classic one; `GameSession.to_state()`/`restore()` persist the
      per-game topology, defaulting to `CLASSIC_TOPOLOGY` when the key is
      absent so already-persisted production games (saved before this
      change) keep restoring correctly.
      Updated `static/API.md` (new "Generated Maps" section, `map_mode` on
      the two create endpoints, the new `GameState` fields, and fixed a
      stale claim that "fog-of-war/espionage isn't implemented" left over
      from before the `SPY` work) and `static/RULES.md` (a short note under
      "The Map" pointing at the new query param and fields).
      **Deliberately out of scope at the time, per the plan**:
      `static/player.html` hardcoded the classic map's topology/layout
      client-side and would've mis-rendered a generated game — **since
      fixed, see the item directly below.** `engine.py` (dead, unimported
      duplicate), `app/gauntlet_runner.py` (its own isolated, hardcoded
      calibration battery), and `agent.py`'s prompt-text map description
      were left alone and still are, consistent with how other features
      this session left the "three independent implementations" gap alone.
- [x] **Make `static/player.html` render and play generated maps.** *(Done
      — verified with a jsdom test driving the page's real script against
      a live local server, one run per map mode: both show 8 rendered
      nodes and an edge count matching that specific game's own
      `state.adjacency` (14 for fixed, a different number for generated —
      proving it's reading the real per-game graph, not a constant), and a
      sampled unit's MOVE-destination dropdown options exactly match
      `state.adjacency[terr]` in both cases. Full pytest suite unaffected
      (5/5) since this is a frontend-only change.)*
      Deleted the `ADJACENCY`/`SUPPLY_CENTERS` JS constants entirely
      (along with the comment flagging them as a duplicate of
      `app/mcts.py`'s copy — actually resolved now, not just noted) in
      favor of reading `state.adjacency`/`state.supply_centers` fresh from
      `GET .../state` every render, via a new `updateTopologyFromState()`
      called at the top of `renderState()`. `TERRITORIES` (the hardcoded
      x/y layout) stays as a **fallback only** for fixed-map games, since
      the backend only computes real `coordinates` for generated ones.
      `drawMapEdges()`'s old "draw once, ever" guard was replaced with a
      signature comparison so edges actually redraw when a new game's
      topology differs from the last one rendered (needed since two
      generated games never share a graph). Also widened the map's
      `viewBox` from `800 480` to `800 500` to match
      `app/map_generator.py`'s actual coordinate scale exactly (was
      slightly clipping generated layouts near the bottom edge).
      Added a "🎲 Random map" checkbox next to the Practice vs Bots button
      — without it there was no way to actually *reach* a generated match
      through the UI even after this fix, since `startPracticeMatch()`
      always called `POST /api/v1/practice` with no query param. Checked,
      it appends `?map_mode=generated`; unchecked (the default), behavior
      is byte-for-byte what it was before this change.
- [x] **Wire up `SPY` orders as a real espionage mechanic.** *(Done —
      verified both with a live practice match over real HTTP (register →
      practice match → submit a `SPY` order → wait for resolution → read
      `GET .../intel`) and with a direct unit-level check of
      `resolve_espionage_orders()` using a crafted third-party DM, so the
      interception filtering itself is proven, not just the plumbing —
      practice-match archetype bots never send private DMs to each other
      (see `app/archetypes.py`: every `generate_messages()` only ever
      addresses `"PUBLIC"`), so the live HTTP test alone couldn't exercise
      that path.)*
      Closed the upstream blocker first: `app/mcts.py`'s `ActionType` enum
      only had `HOLD`/`MOVE`/`SUPPORT` — sending `"action": "SPY"` failed
      pydantic validation (`422`) before `app/treaties_engine.py`'s
      already-written (but unwired, and buggy) `resolve_espionage_orders()`
      could ever run. Added `ActionType.SPY`, and added it to
      `Adjudicator.adjudicate()`'s `HOLD`/`SUPPORT` bucket so a spying
      unit still defends its own territory at strength 1 (+ support/buffs)
      but contributes no attack — "forfeits a tactical move" per
      `PROJECT_HANDOFF.md`.
      Deliberately **did not** wire `app/intel_matrix.py`
      (`IntelligenceVerificationMatrix`)'s belief-state/credibility system —
      it needs a per-faction "line of sight" set that doesn't exist
      anywhere in the current map/game model (the whole board is always
      fully visible to every faction via `GET .../state`; there's no
      fog-of-war over unit positions to pierce). That's a real,
      separate architectural gap — see the new item below — not something
      to fake to make this feature look more complete than it is.
      Instead, reused the field that's actually meaningful today: `Order`
      already had a dead `target_faction` field (see `API.md`'s old note —
      "accepted, not read by the adjudicator" — for `SUPPORT`, still true
      there). For `SPY`, `target_faction` is now real: it names which
      faction to investigate. Rewrote `resolve_espionage_orders()` (it
      previously took `target_destination` as a *territory* and compared a
      message's `recipient` field — a faction name — against that
      territory name, which could never match; a real bug in code that had
      never run) to instead return, per resolved `SPY` order: every `MOVE`
      order `target_faction` actually submitted that turn (real intel —
      orders are otherwise hidden from everyone until the whole turn
      resolves simultaneously) and the content of every private
      (non-`PUBLIC`) message that turn involving `target_faction` where the
      spying faction wasn't already a party (a DM to/from you directly is
      already visible via `GET .../messages`).
      Results are secret: added `GameSession.intel_reports` (persisted like
      everything else via `to_state()`/`restore()`) and a new
      `GET /api/v1/games/{game_id}/intel` endpoint, authenticated the same
      way as messages/orders (`get_authorized_faction`), filtered to
      `spying_faction == agent_faction` — confirmed via a second registered
      agent seeing an empty list for its own game. `GET .../state` (fully
      public, no auth) never includes intel content — only a redacted
      public event (`"🕵️ Blue ran an espionage operation against Red."`)
      naming the spy and target, not what was found, mirroring how treaty
      breaches are logged publicly without leaking treaty details that
      aren't the victim's own.
      Updated `static/API.md` (new "Espionage Intel" section, `SPY` added
      to the orders table, corrected the old `target_faction`-is-dead note
      to carve out the `SPY` exception) and `static/RULES.md` (new
      "Espionage" section, replacing the old "Not Yet Active" stub that
      described this exact gap).
      **Not done, and deliberately out of scope for this pass:**
      - No frontend for it — `static/player.html`'s orders form only has
        `HOLD`/`MOVE`/`SUPPORT` in its action dropdown, same as treaty
        proposals having no UI there either (see "Frontend wiring" below).
        A human can still do this today via a raw `curl`/HTTP call, same
        as an agent would.
      - `engine.py` (the standalone independent implementation) and
        `agent.py`'s reference prompt schema (`"enum": ["HOLD", "MOVE",
        "SUPPORT"]`) weren't touched — consistent with how the treaty
        Perfidy Rule was only wired into `app/mcts.py`'s `Adjudicator`, not
        propagated to the other two independent rule copies (see
        "Consolidation" below).
      - `app/archetypes.py` bots never issue `SPY` orders themselves — they
        don't gain any benefit from this new mechanic, only human/real
        agents interacting with the API directly do.
- [ ] **`app/intel_matrix.py`'s belief-state/credibility system remains
      fully unwired.** `IntelligenceVerificationMatrix.synthesize_belief_state()`
      / `.audit_ground_truth()` both require a per-faction "line of sight"
      set as input, and no such concept exists in the current game model —
      the entire board is always visible to everyone via `GET .../state`.
      Before this module could do anything, someone has to decide what
      "line of sight" even means here (adjacency to your own units? a
      fixed radius? something `SPY` orders extend?) and implement an actual
      per-faction partial-visibility map — a real design decision and a
      much bigger change than the `SPY` order mechanic above, which
      deliberately didn't require it.

## Gameplay logic gaps

- [x] **Reduce the DIPLOMACY phase from 120s to 30s.** *(Done — a deliberate
      pacing change, not a bug fix; requested to make matches (human or
      practice) move faster. `GameSession.__init__` and the next-turn reset
      in `resolve_turn()` (`app/main.py`) both set `self.time_remaining =
      30` for a new/continuing DIPLOMACY phase — the ORDERS phase's own 30s
      (`step_phase()`) was already that value and is unaffected. Updated
      the three docs that quoted the old duration:
      `static/RULES.md` ("DIPLOMACY (120s)" → "(30s)"), `static/API.md`
      (`POST /api/v1/games`'s description of a freshly created game's
      starting clock), and `static/index.html`'s "The Process" copy. Full
      backend test suite still 5/5 after the change (none of the 5 tests
      assert on the specific timer value, only on phase transitions).)*
- [x] **Fix a silent unit-erasure bug in `Adjudicator.adjudicate()`.** *(Not on
      the original list — found by actually playing a simulated game turn by
      turn (see "how to observe the engine" below) and cross-checking one
      turn's printed events against the resulting map by hand, then confirmed
      with a minimal deterministic repro. Fixed and reverified against the
      same repro plus the full test suite and four other resolution paths
      (head-to-head swap, 3-way tie, supported dislodge, plain hold) to
      confirm no regressions.)*
      `app/mcts.py:146` (now restructured) resolved territories one at a time
      in `ADJACENCY`'s fixed dict order, writing into one shared
      `surviving_units` dict for two different things: "who wins this
      territory as an attack target" and "an attacker bouncing back to its
      own origin after a failed attack elsewhere." When a unit's home
      territory was independently captured by a third party's successful,
      unopposed move the same turn the home unit was away attacking (and
      failing), the later "bounce back to origin" write silently overwrote
      the earlier, correct capture — erasing the successful mover from the
      map entirely with no elimination event logged; the printed event log
      ("X moved to Y successfully") directly contradicted the resulting
      state. It was order-dependent on `ADJACENCY`'s declaration order, not
      random — reproducible every time, not a flake.
      Fix: split the single `surviving_units` dict into `dest_occupant`
      (populated once per territory, during that territory's own resolution
      as an attack/hold target) and `origin_bounce_back` (populated once per
      failed attacker, keyed by the territory they're returning to), then
      merge with `dest_occupant` taking priority — matching standard
      Diplomacy semantics: a failed attacker only returns home if nothing
      else took that square the same turn. A returning unit that finds its
      home already taken is now eliminated with an explicit event logged,
      instead of silently vanishing.
      **How to observe the engine playing a full game** (useful for spotting
      this kind of thing again): there's no committed script for this, but
      `app/mcts.py`'s `SimState`/`Adjudicator`/`FastAdjudicator` and
      `app/archetypes.py`'s bots (`PacifistTurtle`, `OpportunisticGreedy`,
      `MachiavellianTraitor`, `StochasticChaos`) can be driven directly in a
      throwaway script to play out a 10-turn match instantly (no real-time
      waiting) printing orders/events/scores each turn — much faster than
      driving the real HTTP API's real-time phase timers, and it's how this
      bug was actually found rather than just reasoned about.

- [x] **Make treaty breaches actually affect combat.** *(Done — verified
      at four independent layers, each catching something the previous
      one couldn't: (1) direct Python repro of the exact same attack with
      vs. without the buff — a supported 2-strength attack that conquers
      Centerlands unbuffed, and is defended successfully once buffed
      (2v2 tie, defender wins), proving the adjudication math itself is
      correct; (2) `test_master_e2e_betrayal_pipeline` rewritten per this
      item's own instruction — it previously asserted around the gap
      (its own comment said so); now asserts both outcomes explicitly,
      using a support-based scenario deliberately chosen so the buff
      changes the result, not a 1v1 tie the defender would've won anyway;
      (3) a live HTTP test against the real running server covering
      propose/sign/list and their validation and auth edge cases
      (self-proposal, bogus treaty type, bogus territory, wrong faction
      signing, visibility scoped to the two parties only); (4) a live
      test waiting through the *real* DIPLOMACY/ORDERS timers, confirming
      the automatic timer-triggered `resolve_turn()` (not a manual Python
      call) genuinely invokes the treaty engine and logs the breach
      publicly — plus a separate check that `TreatyAndEspionageEngine`'s
      new persistence survives a real server restart with the reloaded
      `TreatyStatus`/`TreatyType` values being genuine Enum instances
      (`is`, not just `==`), not just coincidentally-equal strings. Full
      test suite still 5/5.)*
      Found and fixed a real pre-existing bug while wiring this in, before
      it ever shipped: `defensive_buffs` was never cleared, so — despite
      `PROJECT_HANDOFF.md` describing the bonus as applying "during the
      *subsequent* resolution" (one turn) — it would have silently kept
      applying to every future turn's combat at that territory for the
      rest of the match once triggered. Now reset at the top of
      `evaluate_orders_for_breaches()` each turn.
      This item's scope turned out bigger than its own description
      implied: there were **no treaty endpoints at all** yet (`propose_treaty()`/
      `sign_treaty()` existed only as engine methods nothing ever called) —
      threading `defensive_buffs` into `Adjudicator.adjudicate()` alone
      wouldn't have been reachable by anyone. Added
      `POST .../treaties` (propose), `POST .../treaties/{id}/sign`, and
      `GET .../treaties` (visible only to the two parties involved) to
      `app/main.py`, gated to the DIPLOMACY phase like messages.
      `GameSession` gained a `treaty_engine` (persisted via new
      `TreatyAndEspionageEngine.to_dict()`/`from_dict()`, since
      `SmartTreaty` is a plain dataclass, not pydantic, so it couldn't
      just reuse the `model_dump()` pattern everything else uses).
      `Adjudicator.adjudicate()` and `FastAdjudicator.step()` both gained
      an optional `defensive_buffs` parameter, applied only to a
      defending `HOLD`/`SUPPORT`-hold's strength, never to an attacking
      `MOVE` — with an explicit `recent_events` line whenever a buff
      actually gets used, matching every other combat detail already
      being logged there.
      Updated `static/RULES.md` (moved treaties out of "Not Yet Active"
      into their own real section, describing exactly what's implemented
      including the `SUPPORT_PROMISE`-isn't-breach-checked caveat) and
      `static/API.md` (all three new endpoints documented, plus why the
      sign-rejection error message is deliberately non-specific about
      *why* a sign attempt failed).

## Frontend wiring

- [x] **Wire up `static/player.html` for real.** *(Done — it was previously
      a pure UI mockup: `sendMessage()`'s `fetch()` call was commented out
      and `submitOrders()` had a bare `// Logic ... goes here` comment, so
      clicking "Play" never actually created or joined a game. Verified
      with a genuinely rigorous method given no real browser was available
      in this environment (Claude-in-Chrome wasn't connected): installed
      jsdom and executed this exact file's actual `<script>` inside a real
      DOM against the live local server — not a mock, not just reading the
      code. Pre-queued 3 synthetic bot agents, then drove the page's own
      `handleJoinClick()`/`sendMessage()`/`submitOrders()` functions and
      waited through the *real* 120s DIPLOMACY + 30s ORDERS timers.
      Confirmed: real registration and matchmaking (assigned a real
      faction and `game_id`); state polling renders turn/phase/timer/owned
      units correctly; a chat message round-tripped through a real
      `POST .../messages` and was picked back up by polling with correct
      de-duplication; the ORDERS-phase form rendered the right owned
      unit, and its `MOVE` destination dropdown exactly matched the
      server's real adjacency data; order submission succeeded and the
      turn genuinely advanced (1 → 2) after the real timer elapsed. Also
      separately unit-tested the `SUPPORT` order UI in isolation (source
      dropdown listing all occupied territories, destination dropdown
      correctly updating to `[source, ...its adjacency]` when the
      supported unit changes) since the live run's single-unit bot never
      exercised that path. Full backend test suite still 5/5 throughout
      (unaffected).)*
      Added a join screen (display name → register → queue → poll until
      matched) persisted via `localStorage` so a page refresh resumes an
      in-progress match instead of losing it; a finished-game banner with
      a "Register New Agent" reset. Two honest gaps this surfaced, not
      fixed here:
      - **There's still no way to leave the *real* queue.**
        `app/server_hub.py`'s `matchmaking_queue` only ever pops agents
        once 4 accumulate — there is no "leave queue" endpoint, so a solo
        human who clicks "Find Match" genuinely queues forever until 3
        more real agents join too. Addressed *practically* (not fixed
        directly) by the practice-match feature below — anyone stuck can
        just click "Practice vs Bots" instead — but the underlying
        limitation on the real queue is still there.
      - Confirmed **`static/leaderboard.html` is 100% fake** — `mockData`
        is a hardcoded array, there is no `GET /api/v1/leaderboard`
        endpoint, and `AgentRecord.elo_rating` (`app/server_hub.py`) is
        never updated by anything after a match. Building a real one needs
        `app/main.py`'s `resolve_turn()`/game-finish path to actually call
        `app/trueskill_engine.py` (now the sole rating engine — see the
        canonical-rating-system item below) and persist the result
        somewhere queryable — a meaningfully larger task than this item,
        not attempted here. **Since done — see "Wire TrueSkill into
        game-finish + persist agents" further down.**
- [x] **Add a practice-match mode (`POST /api/v1/practice`).** *(Done —
      the direct fix for the "solo human queues forever" gap above: lets
      anyone play immediately against the existing archetype bots
      (`app/archetypes.py` — the same ones the gauntlet already uses)
      instead of waiting for 3 more real agents. Verified rigorously with
      jsdom against the real live server, waiting through real 120s/30s
      phase timers: practice match starts instantly (no queue wait);
      bot-generated diplomacy messages genuinely round-trip through the
      real messages pipeline (confirmed `PacifistTurtle`'s exact message
      text appearing in chat); and — the most important check — **both
      `OpportunisticGreedy` bots assigned that turn independently and
      correctly grabbed adjacent neutral Supply Centers in the same real
      turn resolution as the human's own submitted order** (`Red:
      Northreach→Centerlands`, `Green: Sunport→Southvale`), proving bots
      genuinely drive multiple simultaneous factions, not just one. Also
      verified clicking "Practice" again mid-match doesn't spawn a second
      game. Full backend test suite still 5/5 throughout.)*
      `GameSession` gained `bot_factions: Dict[faction, archetype_class_name]`
      (persisted like everything else) and two methods:
      `run_bot_diplomacy()` (called once per turn at DIPLOMACY start) and
      `run_bot_orders()` (called once per turn at ORDERS start, so bot
      orders are already present in `self.orders` before the real timer
      elapses and `resolve_turn()` reads it — no special-casing needed in
      `resolve_turn()` itself). Both convert the session's map to a
      `SimState` via a new `SimState.from_territory_map()` classmethod
      (`app/mcts.py`) — the missing inverse of `FastAdjudicator.step()`'s
      existing conversion — so the archetypes' existing `SimState`-shaped
      interface didn't need to change at all.
      The new endpoint reuses `server_hub.assigned_matches` (the exact
      same structure the real matchmaker populates), so every existing
      per-game auth/messages/orders code path (`get_authorized_faction()`
      etc.) needed zero changes. Deliberately allows starting a *new*
      practice match with the same identity once a previous *practice*
      match has finished (checked via `bot_factions` + `phase ==
      FINISHED`) — real matches still don't support this, consistent with
      the existing "once matched, always matched" limitation.
      `static/player.html` gained a "Practice vs Bots" button (shares a
      registration helper with "Find Match" rather than duplicating it), a
      bot-opponents indicator in the header (archetype names
      humanized: `MachiavellianTraitor` → "Machiavellian Traitor"), and a
      "Practice Again" option on the finished-game banner (real matches
      still only offer "Register New Agent", since they can't be
      restarted). Fixed a real bug caught before it ever shipped: reusing
      the same page/identity for "Practice Again" would have carried over
      stale per-game client state (`seenMessageIds`, old chat DOM) into
      the new game, since server-assigned message ids are only unique
      *within* a single game — `showGameView()` now resets all of that
      whenever a new game is actually entered.
      `GET /api/v1/games` gained an `is_practice` boolean per game
      (surfaced as a small tag in `static/index.html`'s "Live Games"
      list); `GET .../state`'s `bot_factions` field is included publicly
      so any client can be honest about which opponents are simulated.
      Also retroactively documented `caster_script` in `static/API.md`,
      which had been added to the API earlier this session but never
      written up there.
- [x] **Add `GET /api/v1/games`.** *(Done, small addition alongside the
      above — there was previously no way to see what games exist at all
      without direct DB access; you had to already know a `game_id`.)*
      Returns `{"games": [{game_id, turn, phase, scores, winner}, ...]}`
      for every game currently held in memory. Public, no auth, same
      philosophy as `GET .../state`. Surfaced visibly via a new "Live
      Games" section on `static/index.html` (auto-refreshes every 5s) —
      verified it correctly reflected the real game created during the
      jsdom test above.
- [x] **Add a live visual map to `static/player.html`.** *(Done — a human
      player previously had no board view at all, just the raw orders
      form; `static/playground.html` already had a decorative SVG map for
      its sandbox mode, so this reused its visual style (territory
      circles, SC stars, colored unit tokens) for the real game state.
      One correctness fix over the source it was styled after:
      playground.html's map draws its edges from 11 hardcoded `<line>`
      elements that are actually wrong for the real graph (they omit
      Eastgate's real connections entirely and include a fabricated
      Centerlands↔Duneport edge that doesn't exist in `ADJACENCY`) — since
      this map reflects a real game, `player.html`'s edges are instead
      derived programmatically from its own `ADJACENCY` constant, so they
      can't drift from the graph the server actually adjudicates against.
      Verified with jsdom against the real live server (installed fresh
      into a scratch npm project — no jsdom install persisted from
      earlier in this session): drove the page's own `handlePracticeClick()`
      to get a real 4-faction practice match going, then asserted on the
      rendered SVG DOM itself (not on the page's internal JS variables,
      which — being top-level `let`/`const` in a classic script — don't
      become `window` properties the way top-level `function`s do, a
      scoping quirk that cost a couple of debugging iterations before
      switching the test's assertions to DOM output): exactly 14 edge
      lines drawn, matching the real `ADJACENCY` graph's unique-pair count;
      all 8 territories rendered as nodes; all 4 starting units' faction
      letters (R/B/G/Y) present; and the human's own unit specifically
      (not just "a" unit) carries the gold highlight ring, cross-checked
      against `myFactionLabel`'s actual DOM text.)*
      `renderMap(state.map)` is called from the existing `renderState()`
      poll handler, so it updates on the same 2s cadence as everything
      else — no separate polling loop.

## Consolidation (multiple implementations of the same thing)

- [x] **Decide the canonical game-rules implementation and archive/delete the
      others.** *(Done — verified: `pytest tests/` stays 5/5 (nothing
      imported `engine.py` or exercised `agent.py`'s prompt at test time);
      `python -c "import ast; ast.parse(open('agent.py').read())"` confirms
      `agent.py` still parses cleanly after the template change; a
      repo-wide grep for `engine.py`/`engine:app`/`from engine import`
      turns up nothing left except historical mentions in this file's own
      past-tense entries.)*
      Chose deletion over archiving for `engine.py`. Map topology +
      adjudication logic had existed independently in `app/mcts.py` (used
      by `app/main.py`, the only server this project runs), root
      `engine.py` (a separate standalone FastAPI+WebSocket server), and
      root `agent.py` (rules restated as prose inside its system-prompt
      string). `app/mcts.py` was already the de facto canonical copy —
      every feature shipped this session (auth, treaties, practice mode,
      espionage, generated maps) only ever landed there.
      `engine.py` **deleted outright**: confirmed via a full read plus a
      repo-wide grep that it was genuinely dead (no imports from `app/`,
      nothing in the repo imports/runs it, no CI/systemd/Docker reference —
      `docker-compose.yml`'s `diplomacy-engine` service name is a naming
      coincidence, it builds `Dockerfile`, which runs `uvicorn
      app.main:app`), and that its own game logic was a strict subset of
      `app/mcts.py`'s (missing treaties, espionage, practice mode, real
      matchmaking, persistence, generated maps). Worth recording explicitly
      since it's not risk-free: `engine.py` did have one real capability
      `app/main.py` doesn't — a WebSocket endpoint pushing live state
      updates, vs. `app/main.py`'s pull-only `GET .../state` (polled every
      2s by `player.html`) — but nothing in the repo ever consumed it (no
      client anywhere opened a WebSocket), so nothing broke by removing it.
      If real-time push delivery is ever wanted, build it fresh against
      `app/main.py` rather than trying to resurrect this file.
      `agent.py` **fixed instead of deleted** (it's a real reference
      client, not dead code): added `format_map_block(state)`, which builds
      the "MAP TOPOLOGY & SUPPLY CENTERS" prompt block from a live
      `GET .../state` response's `adjacency`/`supply_centers` fields;
      `SYSTEM_PROMPT` now has a `{map_block}` placeholder instead of 8
      hardcoded territory lines, filled in at both call sites
      (`handle_diplomacy_phase`, `handle_orders_phase`) from the `state`
      dict each already has in hand — the prompt was already being rebuilt
      fresh every phase-handler call, never cached, so this needed no
      restructuring. It now correctly describes a generated-map game too,
      not just the classic one. Did **not** add `"SPY"` to `agent.py`'s
      `ORDER_TOOL`/`DIPLOMACY_TOOLS` JSON schemas (still
      `["HOLD", "MOVE", "SUPPORT"]`) — giving the reference agent actual
      espionage capability is a separate task from fixing its map
      description.
      Confirmed out of scope, no changes needed: `app/swarm_agent.py`
      (never hardcoded the map — always passed the server's raw state dict
      straight into its prompts) and `prompts.yaml` (generic
      strategic-doctrine text, no map content at all).
      `static/player.html`'s order-submission UI was briefly a fourth
      hardcoded copy of the map — already fixed earlier this session (see
      "Wiring the disconnected subsystems" above, the `map_generator.py`
      item): it fetches `adjacency`/`supply_centers`/`coordinates` fresh
      from `GET .../state` every render instead of a local constant.
      **`app/mcts.py` is now the sole game-rules implementation** — updated
      `CLAUDE.md`'s architecture section to match (deleted the "Two
      parallel, non-interoperating implementations" framing along with the
      now-nonexistent `uvicorn engine:app` run instructions).
- [x] **Decide the canonical rating system.** *(Done — verified: `pytest
      tests/` stays 5/5 (`tests/test_integration.py` already only imported
      `app.trueskill_engine`, never `app.elo_calibrator`); a repo-wide grep
      for `elo_calibrator`/`WeightedEloCalibrator` turns up nothing left
      except historical mentions in this file's own past-tense entries and
      `handover.md`'s already-updated gap list.)*
      `app/trueskill_engine.py` (used by `app/gauntlet_runner.py` and
      `tests/test_integration.py`) and `app/elo_calibrator.py` (fully
      standalone — confirmed via grep it was only ever exercised by its own
      `if __name__ == "__main__"` demo, imported nowhere else) were two
      independent implementations of the same Diplomacy-Bench-weighted
      rating idea. Chose TrueSkill: already the one every real consumer in
      the repo used, and a better fit for a 4-player free-for-all (models
      per-player uncertainty via σ, not just a single skill number).
      `app/elo_calibrator.py` **deleted** — same treatment `engine.py` got
      for the rules-consolidation item above, for the same reason (dead,
      standalone, zero real consumers).
      **This does not make the leaderboard real** — that's a separate,
      already-noted gap (see "Confirmed `static/leaderboard.html` is 100%
      fake" above): `AgentRecord.elo_rating` still isn't updated by
      anything after a match, since nothing in `app/main.py`'s
      `resolve_turn()`/game-finish path calls `app/trueskill_engine.py` at
      all yet. This item only removed the redundant second implementation
      of the rating math itself; wiring the surviving one into an actual
      post-match update + a real `GET /api/v1/leaderboard` endpoint is
      unstarted and meaningfully larger.
- [x] **Wire TrueSkill into game-finish + persist agents, so the
      leaderboard is real.** *(Done — verified: unit-level check of
      `rate_finished_game()` directly (a hand-built 4-agent tie scenario:
      confirmed `wins` correctly credited to both tied factions, rank-1's
      `mu` increased, rank-4's decreased, and a practice-match
      `GameSession` was skipped entirely with zero mutation); a
      persistence round-trip (register an agent, full process restart,
      confirm it's still there, still authorized to submit orders in its
      in-progress game); and the real thing — 4 real agents registered,
      driven through the actual matchmaker queue into one real game,
      never submitting any orders (guaranteed Turn-10 4-way tie), left
      running for real across a long, unplanned gap (a session
      interruption spanning several hours) with no attention — confirmed
      the game kept resolving correctly the entire time with no
      supervision, finished with all 4 agents credited `wins=1`/
      `win_rate=100.0` and distinct `conservative_mmr`s, and all of it
      survived a subsequent full server restart. Full pytest suite
      unaffected throughout (5/5).)*
      This surfaced a real prerequisite that wasn't obvious upfront:
      `app/server_hub.py`'s `agents_db`/`agent_id_lookup`/
      `assigned_matches` were plain in-memory dicts, never touched by
      `app/db.py` — a server restart already wiped every registered
      agent's API key and match assignment, independent of ratings.
      Fixed via two new SQLite tables (`app/db.py`'s `AgentRow`/
      `AssignedMatchRow`, same JSON-blob-per-row pattern as the existing
      `GameRecord`) and restore logic in `lifespan()`. This incidentally
      fixes a latent bug: restarting mid-game used to leave every real
      agent 403'd out of its own already-resumed game, since
      `get_authorized_faction()` depends on `assigned_matches` surviving.
      `matchmaking_queue` (agents waiting, not yet matched) is
      deliberately **not** persisted — losing queue position on restart
      is a minor re-join-once inconvenience, not the same class of bug;
      a small, explicitly deferred follow-up.
      `AgentRecord.elo_rating` (dead, hardcoded `1200.0`, never written by
      anything - leftover from the deleted `app/elo_calibrator.py`) is
      **removed**, replaced with real `mu`/`sigma`/`conservative_mmr`/
      `wins` fields mirroring `TrueSkillProfile` (`matches_played`
      already existed, now actually incremented) - a public API response
      shape change on `POST /api/v1/agents/register`, flagged explicitly
      since it never carried real data either way.
      New `async def rate_finished_game()` (`app/main.py`), called from
      `game_loop()` right after a step transitions a game to `FINISHED`.
      Skips practice matches entirely (`game.bot_factions` non-empty) -
      archetype bots have no `AgentRecord`, and this mirrors how
      `app/gauntlet_runner.py`'s own bot-vs-candidate calibration battles
      already never touch `agents_db` (fresh, throwaway registry per
      call). Builds a `faction -> agent_id` map by scanning
      `assigned_matches` for the finishing `game_id` (no such reverse
      lookup existed before); skips (rather than guesses) if it doesn't
      find all 4, covering e.g. an admin-created `POST /api/v1/games`
      game with nobody matched into it. Ranks factions by final SC count
      (same stable-sort convention `app/gauntlet_runner.py` already uses
      for `placement_rank`), feeds neutral constants for TrueSkill's
      "Diplomacy-Bench modulators" (`persuasion_index=0.5`,
      `betrayal_efficiency=1.0`, `deception_resilience=0.5` - collapses
      the bench-modulator multiplier to exactly `1.0`, i.e. pure
      TrueSkill), and persists the result.
      **Two honest, disclosed limitations, not fixed here:**
      - No real per-match persuasion/betrayal/deception scoring is
        derived from actual message/treaty history yet (see the neutral
        constants above) - a separate, meaningfully larger task.
      - A tied game result (e.g. two factions finishing with equal SCs)
        is fully honored in `wins`/`win_rate` for every tied agent, but
        `BayesianMMREngine` itself has no representation for a tied
        placement - its adjacent-pairwise algorithm always treats sorted
        index *i* as strictly beating index *i+1*, so tied factions still
        get distinct (arbitrary-among-equals) placements for the actual
        `mu`/`sigma` adjustment. This is a pre-existing limitation of the
        shared rating engine, not something this hook works around -
        confirmed directly in the E2E test above (all 4 agents tied and
        credited a win, but their `conservative_mmr`s ended up different,
        not identical).
      New public `GET /api/v1/leaderboard` (no auth, same convention as
      `GET /api/v1/games`): every agent, sorted by `conservative_mmr`
      descending. `static/leaderboard.html` now fetches this for real
      instead of `mockData` - also dropped the vendor-family filter
      bar/badge and the "Betrayal Eff" column, since neither has an
      honest per-agent data source (`AgentRecord` has no vendor field,
      and betrayal efficiency isn't a stored per-agent stat, just a
      per-match input defaulted to a neutral constant above); relabeled
      "Elo Rating" → "MMR" since it's real TrueSkill `conservative_mmr`
      now, not Elo.
      Updated `static/API.md` (new "Leaderboard" section, the
      `elo_rating`-removed/new-fields note on registration, and the
      persistence/tie caveats above) and `CLAUDE.md`'s "Rating system"
      section.
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
