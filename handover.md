# Handover

Snapshot of where this project actually stands, for picking the work back up
cold (human or AI). `TODO.md` has the detailed, verified-line-by-line record
of every fix; this is the short version plus what to know before you touch
anything.

## Latest session (2026-09-27)

Completed **all 3 QoL gaps** and added onboarding infrastructure:

**Frontend QoL (3 gaps closed):**
1. **SPY Orders UI** (`player.html`) - added "SPY" as 4th action type in command deck; polls `/api/v1/games/{id}/intel` to display intercepted enemy orders/messages in tabbed "Intel" panel alongside "Messages"
2. **Live Game Spectator** (`spectator.html`) - transformed from static preview into fully functional viewer: game ID selector, polls state every 1s, renders live battle map (supports both fixed & generated maps), displays real caster commentary from server's `caster_script` array on dual-host broadcast desk (Rex Viper + Dr. Evelyn)
3. **Espionage Intel Display** - intercepted intel from successful SPY operations now shows in player.html with observed moves and private messages captured; badge counts total intel packets gathered

**Onboarding/Documentation:**
- **`build.html`** - new primary entry point for building agents: pick LLM foundation (OpenAI/Claude/Ollama/custom API), get personalized API key setup, copy-paste agent code templates for each model, starter prompt scaffold; prominently linked from index.html
- **MIT LICENSE** - open-source ready
- **Comprehensive README** - quick-start guide with live site link, features, dev setup
- **Prompt Playground expansion** - sandbox simulation extended from 3 turns to full 10-turn narrative arc showing strategy evolution, diplomacy/betrayal dynamics, victory condition, post-game TrueSkill impact
- **`prompts.yaml` removed from repo** - moved into playground.html's default preset UI; folded cleanly with no loss of content

**Live status:** All 8 commits deployed to `https://diplomacy.nzdataconsulting.co.nz` and verified responding.

## Repo state right now

- Git repo (`main` branch), **working tree clean, everything committed and
  pushed** to `https://github.com/AmbiguousError/micro-diplomacy.git` -
  check `git log --oneline` for the current commit count/history rather
  than trusting a specific number here, it goes stale immediately.
  **This repo must stay public** for the Mac Mini's deploy loop below to
  work - it once went private mid-session (cause unknown; not something
  this session did deliberately) and `git pull` on the Mac Mini started
  failing with a `401` until it was set back to public
  (`gh repo edit ... --visibility public`). If a deploy ever fails with
  `"could not read Username for 'https://github.com'"`, check
  `gh repo view --json visibility` first before assuming it's a network or
  server problem.
- `venv/` exists with everything installed (`requirements.txt` +
  `requirements-dev.txt`). `pytest` (bare, no `python -m`) is 5/5.
- Runs locally via `uvicorn app.main:app --reload --port 8000`, or via
  `docker build .` / `docker-compose up` - both verified working, including
  SQLite persistence surviving a restart either way.
- **It's deployed and live in production**, not just a local project:
  `https://diplomacy.nzdataconsulting.co.nz`, running on a real Mac Mini
  (SSH alias `root@body`, reachable over Tailscale, Debian 13), as
  `systemd` service `micro-diplomacy.service`, fronted by a Cloudflare
  Tunnel. Deploy loop for every change so far: commit locally → `git push` →
  `ssh root@body 'cd micro-diplomacy && git pull'` → `systemctl restart
  micro-diplomacy.service` → spot-check the live URLs with `curl`. There is
  no CI/CD - this manual loop *is* the deploy process right now.
- Static frontend is root-mounted (`app.mount("/", StaticFiles(directory=
  "static", html=True))`), so pages serve at bare paths - `/player.html`,
  `/RULES.md`, `/index.html` - **not** under a `/static/` prefix. Easy to
  get wrong when curling the live site to verify a frontend change.

## What's actually live and working

- Core game engine (`app/mcts.py`): map, phases, `HOLD`/`MOVE`/`SUPPORT`,
  adjudication. A real silent-unit-erasure bug was found and fixed here -
  see `TODO.md`'s gameplay-logic-gaps section for the exact repro.
- Persistence: SQLite via SQLAlchemy async (`app/db.py`), not Postgres -
  `docker-compose.yml`'s earlier Postgres setup was actively wrong and got
  removed. Game state survives a process restart (bare-metal and Docker,
  both verified).
- **Auth is a real per-agent system, not the faction name.** Register via
  `POST /api/v1/agents/register`, join `POST /api/v1/queue/join`, poll
  `GET /api/v1/queue/status` until matched - game_id and faction are
  assigned by a matchmaker, not chosen by the caller. `agent.py` and
  `app/swarm_agent.py` both use the new flow. Full details and JSON shapes:
  `static/API.md`.
- **Practice-match mode**: `POST /api/v1/practice` drops a human straight
  into a live game against 3 archetype bots (`app/archetypes.py`) on the
  other 3 factions, no waiting for real matchmaking. `player.html`'s
  "Practice vs Bots" button drives this.
- **Treaty breaches now actually affect combat (the Perfidy Rule is
  wired).** `TreatyAndEspionageEngine`'s defensive buff on a breach victim
  is read by `Adjudicator.adjudicate()` - this used to be the single
  biggest "the benchmark isn't testing what it claims" gap; it's closed.
- **`player.html` (human command deck) is fully wired to the real API**,
  including a live SVG battle map of current game state - territory
  ownership, Supply Center stars, unit positions/colors, and a gold
  highlight on the viewing player's own unit. Visual style matches
  `playground.html`'s sandbox map, but the edges are derived
  programmatically from the real `ADJACENCY` graph rather than copying
  `playground.html`'s hardcoded lines, which are wrong (missing Eastgate's
  real connections, plus a fabricated Centerlands↔Duneport edge) - worth
  remembering if `playground.html`'s map is ever used as a reference again.
- **`spectator.html` (live game viewer) is now fully wired.** Enter any game ID
  to watch live: polls game state every 1s, displays turn/phase/timer, renders
  live battle map (handles both fixed and generated topologies), and shows
  real caster commentary from the server's generated `caster_script` on a
  dual-host broadcast desk (Rex Viper play-by-play, Dr. Evelyn strategy).
  A "Stop Watching" button returns to game selector.
- **Espionage (`SPY` orders) is fully wired.** A unit given `SPY` forfeits its
  move (defends like a `HOLD`, can't attack) in exchange for that turn's
  real `MOVE` orders and any intercepted private DMs involving
  `target_faction` - delivered privately via `GET .../intel`, never the
  public `GET .../state`. **Frontend now complete:** `player.html` has SPY
  action in order dropdown + tabbed Intel panel showing all intercepted
  operations (observed moves, captured messages), with badge counting total
  intel packets gathered this game. `app/intel_matrix.py`'s separate
  belief-state/credibility system is still unwired - see gap #1 below, it
  needs a real fog-of-war concept that doesn't exist yet.
- **Generated maps are wired.** `?map_mode=generated` on `POST /api/v1/games`
  or `POST /api/v1/practice` (default stays `"fixed"`, so nothing existing
  changed behavior) spins up a game on a randomized planar graph
  (`app/map_generator.py`, SciPy Delaunay) instead of the classic map -
  same 8 territory names/6 SC count, but different adjacency, different SC
  placement, different starting positions every time. `GameSession`,
  `Adjudicator`, `SimState`, and the archetype bots all take a
  `MapTopology` (`app/mcts.py`) now instead of closing over
  `ADJACENCY`/`SUPPLY_CENTERS`/`STARTING_POSITIONS` as globals - those
  globals still exist unchanged and are still what every *fixed*-map game
  uses by default. `GET .../state` exposes a game's real
  `map_mode`/`adjacency`/`supply_centers`/`coordinates`. **`player.html`
  now supports it too**: a "🎲 Random map" checkbox next to "Practice vs
  Bots" requests `?map_mode=generated`, and the page fetches its
  adjacency/coordinates/SC set fresh from `GET .../state` every render
  instead of a hardcoded copy - verified via jsdom against a live server,
  one run per mode, checking rendered node/edge counts and MOVE-dropdown
  options match that specific game's own topology.
- **`app/mcts.py` is now the sole game-rules implementation** - root
  `engine.py` (a standalone, unimported duplicate FastAPI+WebSocket server)
  was deleted outright (it had one real capability `app/main.py` lacks, a
  WebSocket push transport, but nothing in the repo ever consumed it), and
  `agent.py`'s system prompt no longer hardcodes the map as static text -
  `format_map_block(state)` builds it fresh from a live `GET .../state`
  response every phase-handler call, so it correctly describes generated-
  map games too, not just the classic one. `app/swarm_agent.py` and
  `prompts.yaml` never hardcoded the map and needed no changes.
- **DIPLOMACY phase is 30s**, matching the ORDERS phase (both were
  previously 120s/30s respectively; DIPLOMACY was cut for pacing, not a
  bug fix). Consistent across `app/main.py`, `RULES.md`, `API.md`, and
  `index.html`.
- Gauntlet calibration (`POST /api/v1/gauntlet/calibrate/{agent_id}`) is
  wired and works: candidate order-decisions are fetched via HTTP callback,
  matches run instantly (no real-time waiting).
- `GET /api/v1/games` lists running games (used by the leaderboard/landing
  page - this used to be a stubbed/false leaderboard, now backed by real
  state).
- `static/index.html` is a real landing page (root-mounted), linking
  `RULES.md`/`API.md`/`docs.html` (all accurate to current behavior) and
  the interactive pages.
- Caster commentary (`app/dual_caster.py`) generates via LLM after each
  turn resolves and lands in `GET .../state`'s `caster_script` field - but
  as of the last time this was checked, nothing displays it yet, and no
  `OPENAI_API_KEY` had been available to test with a real model (verified
  instead with a mocked client plus a live run confirming graceful failure
  with no key). Re-check whether this is still true before assuming it is.
- **`app/trueskill_engine.py` is now the sole rating engine.** The other
  independent implementation, `app/elo_calibrator.py`'s standalone
  pairwise Elo, was deleted (unconsumed anywhere in the repo - every real
  consumer, `app/gauntlet_runner.py` and `tests/test_integration.py`,
  already only used TrueSkill).
- **The leaderboard is real now.** `rate_finished_game()` (`app/main.py`)
  fires from `game_loop()` whenever a real 4-agent match (never a
  practice match) finishes, updates each agent's TrueSkill rating, and
  persists it. `GET /api/v1/leaderboard` (public) serves every agent
  sorted by `conservative_mmr`; `static/leaderboard.html` fetches it for
  real now instead of mock data (the vendor-family filter/badge and
  "Betrayal Eff" column were dropped - neither had an honest per-agent
  data source). Verified with a real 4-agent game driven through the
  actual matchmaker to a Turn-10 tie - all 4 correctly rated, and it
  survived a full server restart.
  **This required adding persistence for agent registration and match
  assignments** (`app/server_hub.py`'s `agents_db`/`agent_id_lookup`/
  `assigned_matches` were plain in-memory dicts before - a restart used
  to wipe every registered agent's API key, independent of ratings; two
  new SQLite tables in `app/db.py` fix this, and incidentally fix a
  latent bug where a restart left every real agent 403'd out of its own
  already-resumed game).
  **Two disclosed limitations, not fixed here**: no real per-match
  persuasion/betrayal/deception scoring is derived from actual gameplay
  yet (neutral constants are used instead - pure TrueSkill-by-placement);
  and a tied game result is fully honored in `wins`/`win_rate` but the
  underlying `mu`/`sigma` math still can't represent a tie (a
  pre-existing limitation of `BayesianMMREngine` itself, confirmed
  directly in the live verification - see `TODO.md` for the full
  writeup). `matchmaking_queue` (agents waiting, not yet matched) is
  still not persisted - a minor, explicitly deferred follow-up.
- **All prose repo-wide uses UK-style ` - ` instead of em dash** (was
  " — " everywhere, no exceptions - a plain `sed` swap). `player.html`'s
  in-game header and `leaderboard.html`'s table got a real mobile pass
  (stack-on-mobile header, hide-least-essential-column table) - both
  visually confirmed at 390px via headless Chromium screenshots.
  `playground.html` (a desktop-oriented prompt IDE) and
  `spectator.html`/`caster_widget.html` (fixed-resolution OBS overlay
  previews) were deliberately left alone.

## What's not done - biggest gaps first

1. **No real fog-of-war/line-of-sight model.** `app/intel_matrix.py`
   (`IntelligenceVerificationMatrix`, belief-state/credibility tracking
   across bots' self-reported scouting claims) needs a per-faction "line of
   sight" set to do anything, and no such concept exists - the whole board
   is always fully visible to everyone via `GET .../state`. Someone has to
   decide what "line of sight" even means here before this module can be
   wired in; it's a real design decision, not a small fix.
2. **Piper voice models were never fetched** (`voices/` is empty) -
   deliberately not done: it's a binary download needing sign-off first,
   and `app/dual_caster.py`'s synthesis path isn't wired to Piper yet
   either, so fetching them alone wouldn't enable anything. Tackle this
   together with actually wiring Piper synthesis.
   
**Completed this session:** SPY order UI, intercepted intel display, live spectator with caster commentary - all 3 QoL gaps from the previous handover are now closed.

(`PROJECT_HANDOFF.md`'s file index and `static/docs.html)`'s stray
filename `)` are both fixed now - nothing cosmetic left outstanding.)

Full detail, verification notes, and exact repro steps for all of the
above are in `TODO.md` - treat it as the source of truth over this file if
they ever disagree.

## Things worth knowing before continuing

- Every fix this project has gone through was verified against the
  *running* app (real HTTP calls, real timers waited out, or explicit
  mocking where an external key was needed) - not just unit tests. Keep
  doing that; several real bugs here were only found by actually running
  the thing, not by reading code. For frontend/JS-heavy changes, a
  jsdom-against-a-live-server test (execute the page's real `<script>` in
  a real DOM, drive its actual functions, assert on rendered DOM output)
  has proven effective - watch for two harness gotchas: top-level
  `const`/`let` in a classic script never become `window` properties (only
  `function` declarations do - read DOM output instead), and Node's global
  `fetch` doesn't resolve relative URLs the way a browser does (shim it
  with `new URL(url, BASE)`).
- `CLAUDE.md` documents the architecture for future Claude Code sessions
  but was written before the auth migration and everything since - it's
  been patched in spots but **not refreshed end-to-end**. Don't fully trust
  its framing of what's wired in vs. not (e.g. it still describes
  persistence and gauntlet as unwired/broken, which is no longer true);
  cross-check `TODO.md` and this file.
- No `OPENAI_API_KEY` was configured in the dev environment as of the last
  check - anything touching `app/dual_caster.py` or `app/swarm_agent.py`'s
  real LLM calls needs either a real key or mocking to verify. Unknown
  whether one is configured on the production Mac Mini - check there
  before assuming caster commentary works end-to-end live.
- Production deploys are a manual SSH loop, not automated - see "Repo state
  right now" above. There's no rollback tooling beyond `git checkout
  <prior-commit>` on the server and restarting the service.
