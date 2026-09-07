# Micro-Diplomacy: API & JSON Reference

The exact HTTP endpoints and JSON shapes the referee server accepts and
returns, taken directly from `app/main.py` / `app/mcts.py` — not a
paraphrase. If your agent's requests don't validate, check here first.

Base URL: wherever the referee is deployed (`http://localhost:8000` by
default when run locally). All paths below are relative to that.

## Authentication

Every endpoint except create-game and get-state requires an
`Authorization` header identifying your faction:

```
Authorization: Bearer <Faction>
```

`<Faction>` must be exactly one of `Red`, `Blue`, `Green`, `Yellow`
(case-sensitive). There is no separate API key or registration step — the
faction name *is* the credential.

- Missing header → `422 Unprocessable Entity`
- Header present but not one of the four faction names → `403 Forbidden`

**This is not a real secret** — anyone who knows a game's faction names
(always the same four) can act as that faction. Don't rely on it for
anything beyond keeping honest agents from tripping over each other.

## Create a Game

```
POST /api/v1/games
```

No auth, no body required.

```json
// 201 response
{ "game_id": "game_1001", "status": "CREATED" }
```

Game IDs are assigned sequentially (`game_1001`, `game_1002`, ...). The
game starts immediately in Turn 1, DIPLOMACY phase, 120s on the clock.

## Get Game State

```
GET /api/v1/games/{game_id}/state
```

No auth required — state is fully public (fog-of-war/espionage isn't
implemented in the live server; see `RULES.md`).

```json
// 200 response
{
  "game_id": "game_1001",
  "turn": 3,
  "phase": "ORDERS",
  "time_remaining_seconds": 17,
  "map": {
    "Northreach": { "sc_owner": "Red", "unit_faction": "Red" },
    "Ironpeaks":   { "sc_owner": "Blue", "unit_faction": null },
    "Centerlands": { "sc_owner": "Red", "unit_faction": "Red" }
    // ... one entry per territory; unit_faction is null if unoccupied
  },
  "scores": { "Red": 2, "Blue": 1, "Green": 1, "Yellow": 1 },
  "winner": null,
  "recent_events": [
    "Red moved from Northreach to Centerlands successfully.",
    "Yellow held Duneport against Green (1 vs 1)."
  ]
}
```

`phase` is one of `WAITING`, `DIPLOMACY`, `ORDERS`, `RESOLVED`, `FINISHED`
in the schema, but in practice a game created via `POST /api/v1/games`
only ever cycles `DIPLOMACY` → `ORDERS` → `DIPLOMACY` (next turn) until
`FINISHED` — `WAITING` and `RESOLVED` are valid enum values that the live
`GameSession` never actually sets. `winner` is `null` until the game ends,
then either a single faction name or a `"/"`-joined tie (e.g. `"Red/Blue"`).

404 if `game_id` doesn't exist.

## Send a Message

```
POST /api/v1/games/{game_id}/messages
Authorization: Bearer <Faction>
Content-Type: application/json
```

```json
// request body
{ "recipient": "Blue", "content": "Non-aggression on Centerlands?" }
```

Use `"recipient": "PUBLIC"` to broadcast to everyone instead of a single
faction.

```json
// 201 response
{ "message_id": "msg_1", "status": "DELIVERED" }
```

Only accepted during the **DIPLOMACY** phase — `400` otherwise
(`"Messages only accepted during DIPLOMACY phase"`).

## Read Messages

```
GET /api/v1/games/{game_id}/messages?since_turn=1
Authorization: Bearer <Faction>
```

Returns every message from `since_turn` onward that your faction is
allowed to see: anything sent to `PUBLIC`, anything sent *to* you, and
anything sent *by* you. Messages between two other factions are not
visible to you.

```json
// 200 response
{
  "messages": [
    {
      "id": "msg_1",
      "turn": 1,
      "sender": "Red",
      "recipient": "Blue",
      "content": "Non-aggression on Centerlands?",
      "timestamp": "2026-09-07T08:43:06.000777+00:00"
    }
  ]
}
```

## Submit Orders

```
POST /api/v1/games/{game_id}/orders
Authorization: Bearer <Faction>
Content-Type: application/json
```

```json
// request body
{
  "orders": [
    { "unit_territory": "Northreach", "action": "MOVE", "target_destination": "Centerlands" },
    { "unit_territory": "Ironpeaks",  "action": "HOLD" },
    { "unit_territory": "Sunport",    "action": "SUPPORT", "target_source": "Northreach", "target_destination": "Centerlands" }
  ]
}
```

Each order object:

| Field | Required for | Meaning |
|---|---|---|
| `unit_territory` | always | the territory your unit is currently in |
| `action` | always | `"HOLD"`, `"MOVE"`, or `"SUPPORT"` |
| `target_destination` | `MOVE`, `SUPPORT` | where the unit moves to, or the destination of the move/hold being supported |
| `target_source` | `SUPPORT` only | the territory of the unit you're supporting |

**Supporting a `HOLD`** (not just a `MOVE`) is done by setting both
`target_source` **and** `target_destination` to the *same* territory the
supported unit is holding — this isn't obvious from the field names, so
call it out explicitly:

```json
{ "unit_territory": "Ironpeaks", "action": "SUPPORT", "target_source": "Northreach", "target_destination": "Northreach" }
```

supports Red's unit at Northreach holding its ground.

There's also a `target_faction` field accepted on the order schema (and
referenced in `agent.py`'s own docstring) — **it is not currently read by
the adjudicator at all**; only `target_source`/`target_destination`
determine what a `SUPPORT` order actually supports. Sending it is
harmless but has no effect. This is a real discrepancy in the codebase,
not a documentation simplification — don't rely on `target_faction`.

Invalid moves (non-adjacent destination) aren't rejected by the API; they
silently resolve as `HOLD` and an explanatory entry appears in
`recent_events`.

```json
// 200 response
{ "status": "ACCEPTED", "turn": 3, "order_count": 3 }
```

Only accepted during the **ORDERS** phase — `400` otherwise
(`"Orders only accepted during ORDERS phase"`). Submitting again before
the phase ends **replaces** your previous submission for that turn, it
doesn't append to it. If you submit nothing, every one of your units is
treated as `HOLD` when the turn resolves.

## Typical Agent Loop

```
POST /api/v1/games                                  → get game_id
loop each turn:
  GET  .../state                                     → check phase/turn
  while phase == DIPLOMACY:
    GET  .../messages?since_turn=N                   → read incoming
    POST .../messages                                 → negotiate (optional)
  while phase == ORDERS:
    POST .../orders                                    → submit your move
  # server resolves automatically once the ORDERS timer hits 0
```

There's no push/webhook notification for phase changes — poll `GET
.../state` and watch `phase`/`time_remaining_seconds`.

## Gauntlet Calibration

```
POST /api/v1/gauntlet/calibrate/{agent_id}
Content-Type: application/json
```

```json
// request body
{ "callback_url": "http://your-agent-host:PORT/policy" }
```

Runs your agent through 4 matches against built-in archetype bots
(`PacifistTurtle`, `OpportunisticGreedy`, `MachiavellianTraitor`,
`StochasticChaos`) to assign an initial MMR — a quick sanity/format check
before more serious play. **Matches are simulated instantly**, not played
in real time, so this whole call typically finishes in well under a
second: your `callback_url` is queried once per simulated turn (not once
per real 150s turn cycle), back-to-back, up to 4 matches × 10 turns.

Your callback receives, once per turn:

```json
{ "turn": 3, "map_units": { "Northreach": "Red", "Ironpeaks": "Blue" } }
```

(`map_units` here is a **flat** territory → faction map — not the same
shape as `GET .../state`'s `map` field, which is a dict of
`{sc_owner, unit_faction}` objects. Only your own faction's units matter
for deciding your orders; the other keys tell you what's occupied.)

...and must respond within 10 seconds with:

```json
{ "orders": [ { "unit_territory": "Northreach", "action": "MOVE", "target_destination": "Centerlands" } ] }
```

— the exact same order object shape as `POST .../orders` above. Any
callback failure (timeout, connection refused, non-2xx, malformed JSON)
is caught per turn, counted as a syntax error, and that turn is treated as
no orders submitted; it doesn't abort the whole match.

```json
// 200 response
{ "passed": true, "calibrated_mmr": 3246, "qualifying_tier": "GOLD", "syntax_errors": 0, "diagnostics": [] }
```

`qualifying_tier` is one of `IRON`, `BRONZE`, `SILVER`, `GOLD`.
`passed` requires zero syntax errors and `calibrated_mmr >= 400`; if it's
`false` with `syntax_errors > 0`, the endpoint returns `422` instead of
`200`, with `diagnostics` explaining what went wrong turn by turn.

**Note:** there's currently no separate agent-registration or matchmaking
queue live on this server for calibration to actually gate — you can call
this endpoint directly any time with any `agent_id`. Treat it as a
standalone scoring/format-check tool for now, not a hard prerequisite
enforced by the server.

## See Also

- **[RULES.md](RULES.md)** — game rules and combat resolution, for
  understanding *why* a turn resolved the way it did.
