# Handover

Snapshot of where this project actually stands, for picking the work back up
cold (human or AI). `TODO.md` has the detailed, verified-line-by-line record
of every fix; this is the short version plus what to know before you touch
anything.

## Repo state right now

- Git repo (`main` branch), 2 commits so far — **but there's substantial
  uncommitted work in the working tree** (the full `server_hub.py` auth
  migration and the `dual_caster.py` wiring, among other things). Run
  `git status` before assuming the commit log reflects current reality.
- `venv/` exists with everything installed (`requirements.txt` +
  `requirements-dev.txt`). `pytest` (bare, no `python -m`) is 5/5.
- Runs locally via `uvicorn app.main:app --host 127.0.0.1 --port 8000`, or
  via `docker build .` / `docker-compose up` — both verified working,
  including SQLite persistence surviving a restart either way.

## What's actually live and working

- Core game engine (`app/mcts.py`): map, phases, `HOLD`/`MOVE`/`SUPPORT`,
  adjudication. A real silent-unit-erasure bug was found and fixed here —
  see `TODO.md`'s gameplay-logic-gaps section for the exact repro.
- Persistence: SQLite via SQLAlchemy async (`app/db.py`), not Postgres —
  `docker-compose.yml`'s earlier Postgres setup was actively wrong and got
  removed.
- **Auth is a real per-agent system now, not the faction name.** Register
  via `POST /api/v1/agents/register`, join `POST /api/v1/queue/join`, poll
  `GET /api/v1/queue/status` until matched — game_id and faction are
  assigned by a matchmaker, not chosen by the caller. `agent.py` and
  `app/swarm_agent.py` both use the new flow. Full details and JSON shapes:
  `static/API.md`.
- Gauntlet calibration (`POST /api/v1/gauntlet/calibrate/{agent_id}`) is
  wired and works: candidate order-decisions are fetched via HTTP callback,
  matches run instantly (no real-time waiting).
- `static/index.html` is a real landing page (root-mounted), linking
  `RULES.md`/`API.md`/`docs.html` (all accurate to current behavior) and
  the interactive pages.
- Caster commentary (`app/dual_caster.py`) generates via LLM after each
  turn resolves and lands in `GET .../state`'s `caster_script` field — but
  nothing displays it yet (no `OPENAI_API_KEY` was available this session
  to test with a real model; verified instead with a mocked client plus a
  live run confirming graceful failure with no key).

## What's not done — biggest gaps first

1. **Treaty breaches (perfidy) have no effect on combat.** The engine
   computes the defensive buff but `Adjudicator.adjudicate()` never reads
   it. This is arguably the single most "the benchmark isn't testing what
   it claims to test yet" gap.
2. **No espionage.** `SPY` isn't even a valid `ActionType` on the `Order`
   schema — a submitted `SPY` order fails validation before any espionage
   logic could run. `app/intel_matrix.py` (fog-of-war belief state) is
   unwired on top of that.
3. **Three independent copies of the game rules** (`app/mcts.py`,
   root `engine.py`, `agent.py`'s prompt text) — no canonical choice made,
   no consolidation.
4. **Two independent rating systems** (`trueskill_engine.py`,
   `elo_calibrator.py`) — same story, undecided.
5. `app/map_generator.py` unwired (needs `ADJACENCY` etc. moved off
   module-level constants first — a real refactor, not a small one).
6. Cosmetic/small: `PROJECT_HANDOFF.md`'s file index doesn't match the real
   `scripts/`/root layout; Piper voice models were never fetched
   (`voices/` is empty).

Full detail, verification notes, and exact repro steps for all of the
above are in `TODO.md` — treat it as the source of truth over this file if
they ever disagree.

## Things worth knowing before continuing

- Every fix this session was verified against the *running* app (real HTTP
  calls, real timers waited out, or explicit mocking where an external key
  was needed) — not just unit tests. Keep doing that; several real bugs
  here were only found by actually running the thing, not by reading code.
- `CLAUDE.md` documents the architecture for future Claude Code sessions
  but was written before most of this session's work — it's been patched
  for the auth section specifically (since that patch made an old claim
  actively wrong) but **not refreshed end-to-end**. Don't fully trust its
  framing of what's wired in vs. not; cross-check `TODO.md`.
- No `OPENAI_API_KEY` is configured in this environment — anything
  touching `app/dual_caster.py` or `app/swarm_agent.py`'s real LLM calls
  needs either a real key or mocking to verify.
