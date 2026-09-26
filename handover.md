# Handover

Snapshot of where this project actually stands, for picking the work back up
cold (human or AI). `TODO.md` has the detailed, verified-line-by-line record
of every fix; this is the short version plus what to know before you touch
anything.

## Repo state right now

- Git repo (`main` branch), **working tree clean, everything committed and
  pushed** to `https://github.com/AmbiguousError/micro-diplomacy.git` —
  check `git log --oneline` for the current commit count/history rather
  than trusting a specific number here, it goes stale immediately.
  **This repo must stay public** for the Mac Mini's deploy loop below to
  work — it once went private mid-session (cause unknown; not something
  this session did deliberately) and `git pull` on the Mac Mini started
  failing with a `401` until it was set back to public
  (`gh repo edit ... --visibility public`). If a deploy ever fails with
  `"could not read Username for 'https://github.com'"`, check
  `gh repo view --json visibility` first before assuming it's a network or
  server problem.
- `venv/` exists with everything installed (`requirements.txt` +
  `requirements-dev.txt`). `pytest` (bare, no `python -m`) is 5/5.
- Runs locally via `uvicorn app.main:app --reload --port 8000`, or via
  `docker build .` / `docker-compose up` — both verified working, including
  SQLite persistence surviving a restart either way.
- **It's deployed and live in production**, not just a local project:
  `https://diplomacy.nzdataconsulting.co.nz`, running on a real Mac Mini
  (SSH alias `root@body`, reachable over Tailscale, Debian 13), as
  `systemd` service `micro-diplomacy.service`, fronted by a Cloudflare
  Tunnel. Deploy loop for every change so far: commit locally → `git push` →
  `ssh root@body 'cd micro-diplomacy && git pull'` → `systemctl restart
  micro-diplomacy.service` → spot-check the live URLs with `curl`. There is
  no CI/CD — this manual loop *is* the deploy process right now.
- Static frontend is root-mounted (`app.mount("/", StaticFiles(directory=
  "static", html=True))`), so pages serve at bare paths — `/player.html`,
  `/RULES.md`, `/index.html` — **not** under a `/static/` prefix. Easy to
  get wrong when curling the live site to verify a frontend change.

## What's actually live and working

- Core game engine (`app/mcts.py`): map, phases, `HOLD`/`MOVE`/`SUPPORT`,
  adjudication. A real silent-unit-erasure bug was found and fixed here —
  see `TODO.md`'s gameplay-logic-gaps section for the exact repro.
- Persistence: SQLite via SQLAlchemy async (`app/db.py`), not Postgres —
  `docker-compose.yml`'s earlier Postgres setup was actively wrong and got
  removed. Game state survives a process restart (bare-metal and Docker,
  both verified).
- **Auth is a real per-agent system, not the faction name.** Register via
  `POST /api/v1/agents/register`, join `POST /api/v1/queue/join`, poll
  `GET /api/v1/queue/status` until matched — game_id and faction are
  assigned by a matchmaker, not chosen by the caller. `agent.py` and
  `app/swarm_agent.py` both use the new flow. Full details and JSON shapes:
  `static/API.md`.
- **Practice-match mode**: `POST /api/v1/practice` drops a human straight
  into a live game against 3 archetype bots (`app/archetypes.py`) on the
  other 3 factions, no waiting for real matchmaking. `player.html`'s
  "Practice vs Bots" button drives this.
- **Treaty breaches now actually affect combat (the Perfidy Rule is
  wired).** `TreatyAndEspionageEngine`'s defensive buff on a breach victim
  is read by `Adjudicator.adjudicate()` — this used to be the single
  biggest "the benchmark isn't testing what it claims" gap; it's closed.
- **`player.html` (human command deck) is fully wired to the real API**,
  including a live SVG battle map of current game state — territory
  ownership, Supply Center stars, unit positions/colors, and a gold
  highlight on the viewing player's own unit. Visual style matches
  `playground.html`'s sandbox map, but the edges are derived
  programmatically from the real `ADJACENCY` graph rather than copying
  `playground.html`'s hardcoded lines, which are wrong (missing Eastgate's
  real connections, plus a fabricated Centerlands↔Duneport edge) — worth
  remembering if `playground.html`'s map is ever used as a reference again.
- **Espionage (`SPY` orders) is wired.** A unit given `SPY` forfeits its
  move (defends like a `HOLD`, can't attack) in exchange for that turn's
  real `MOVE` orders and any intercepted private DMs involving
  `target_faction` — delivered privately via `GET .../intel`, never the
  public `GET .../state`. No frontend for it yet (same as treaties — see
  the gaps list). `app/intel_matrix.py`'s separate belief-state/credibility
  system is still unwired — see gap #1 below, it needs a real fog-of-war
  concept that doesn't exist yet.
- **Generated maps are wired.** `?map_mode=generated` on `POST /api/v1/games`
  or `POST /api/v1/practice` (default stays `"fixed"`, so nothing existing
  changed behavior) spins up a game on a randomized planar graph
  (`app/map_generator.py`, SciPy Delaunay) instead of the classic map —
  same 8 territory names/6 SC count, but different adjacency, different SC
  placement, different starting positions every time. `GameSession`,
  `Adjudicator`, `SimState`, and the archetype bots all take a
  `MapTopology` (`app/mcts.py`) now instead of closing over
  `ADJACENCY`/`SUPPLY_CENTERS`/`STARTING_POSITIONS` as globals — those
  globals still exist unchanged and are still what every *fixed*-map game
  uses by default. `GET .../state` exposes a game's real
  `map_mode`/`adjacency`/`supply_centers`/`coordinates`. **No frontend for
  it** — `player.html` still hardcodes the classic map client-side (see
  gap #2 below), so it only renders/works correctly for fixed-map games.
- **DIPLOMACY phase is 30s**, matching the ORDERS phase (both were
  previously 120s/30s respectively; DIPLOMACY was cut for pacing, not a
  bug fix). Consistent across `app/main.py`, `RULES.md`, `API.md`, and
  `index.html`.
- Gauntlet calibration (`POST /api/v1/gauntlet/calibrate/{agent_id}`) is
  wired and works: candidate order-decisions are fetched via HTTP callback,
  matches run instantly (no real-time waiting).
- `GET /api/v1/games` lists running games (used by the leaderboard/landing
  page — this used to be a stubbed/false leaderboard, now backed by real
  state).
- `static/index.html` is a real landing page (root-mounted), linking
  `RULES.md`/`API.md`/`docs.html` (all accurate to current behavior) and
  the interactive pages.
- Caster commentary (`app/dual_caster.py`) generates via LLM after each
  turn resolves and lands in `GET .../state`'s `caster_script` field — but
  as of the last time this was checked, nothing displays it yet, and no
  `OPENAI_API_KEY` had been available to test with a real model (verified
  instead with a mocked client plus a live run confirming graceful failure
  with no key). Re-check whether this is still true before assuming it is.

## What's not done — biggest gaps first

1. **No real fog-of-war/line-of-sight model.** `app/intel_matrix.py`
   (`IntelligenceVerificationMatrix`, belief-state/credibility tracking
   across bots' self-reported scouting claims) needs a per-faction "line of
   sight" set to do anything, and no such concept exists — the whole board
   is always fully visible to everyone via `GET .../state`. Someone has to
   decide what "line of sight" even means here before this module can be
   wired in; it's a real design decision, not a small fix.
2. **`player.html` can't render or play a generated map.** It hardcodes the
   classic map's adjacency and SVG layout coordinates client-side (for
   both rendering and client-side move-legality checks), so a
   `map_mode=generated` game will mis-render/wrongly reject legal moves
   there — works fine via direct API calls (agents, `curl`), just not
   through the human UI yet. Fix is to fetch `adjacency`/`coordinates`
   from `GET .../state` instead of the hardcoded constants.
3. **Three independent copies of the game rules** (`app/mcts.py`,
   root `engine.py`, `agent.py`'s prompt text) — no canonical choice made,
   no consolidation. If you change map topology, order semantics, or
   adjudication rules, you have to decide which of these you're targeting.
   (Neither the espionage nor the generated-map work touched `engine.py` or
   `agent.py`'s prompt schema — both are still classic-map/no-`SPY` only.)
4. **Two independent rating systems** (`trueskill_engine.py`,
   `elo_calibrator.py`) — same story, undecided.
5. Cosmetic/small: `PROJECT_HANDOFF.md`'s file index doesn't match the real
   `scripts/`/root layout; Piper voice models were never fetched
   (`voices/` is empty); `static/docs.html)` has a stray trailing `)` in the
   filename.

Full detail, verification notes, and exact repro steps for all of the
above are in `TODO.md` — treat it as the source of truth over this file if
they ever disagree.

## Things worth knowing before continuing

- Every fix this project has gone through was verified against the
  *running* app (real HTTP calls, real timers waited out, or explicit
  mocking where an external key was needed) — not just unit tests. Keep
  doing that; several real bugs here were only found by actually running
  the thing, not by reading code. For frontend/JS-heavy changes, a
  jsdom-against-a-live-server test (execute the page's real `<script>` in
  a real DOM, drive its actual functions, assert on rendered DOM output)
  has proven effective — watch for two harness gotchas: top-level
  `const`/`let` in a classic script never become `window` properties (only
  `function` declarations do — read DOM output instead), and Node's global
  `fetch` doesn't resolve relative URLs the way a browser does (shim it
  with `new URL(url, BASE)`).
- `CLAUDE.md` documents the architecture for future Claude Code sessions
  but was written before the auth migration and everything since — it's
  been patched in spots but **not refreshed end-to-end**. Don't fully trust
  its framing of what's wired in vs. not (e.g. it still describes
  persistence and gauntlet as unwired/broken, which is no longer true);
  cross-check `TODO.md` and this file.
- No `OPENAI_API_KEY` was configured in the dev environment as of the last
  check — anything touching `app/dual_caster.py` or `app/swarm_agent.py`'s
  real LLM calls needs either a real key or mocking to verify. Unknown
  whether one is configured on the production Mac Mini — check there
  before assuming caster commentary works end-to-end live.
- Production deploys are a manual SSH loop, not automated — see "Repo state
  right now" above. There's no rollback tooling beyond `git checkout
  <prior-commit>` on the server and restarting the service.
