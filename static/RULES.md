# Micro-Diplomacy: Rules

This describes the rules **actually enforced by the running referee server**
(`app/mcts.py` + `app/main.py`), not an idealized or planned design. Where a
mechanic exists in the codebase but isn't active yet, that's called out
explicitly below rather than presented as if it works.

## Objective

Four factions — **Red, Blue, Green, Yellow** — compete for control of
Supply Centers on a shared 8-territory map. A faction wins by:

- Controlling **5 of the 6 Supply Centers**, or
- Controlling the **most Supply Centers when Turn 10 ends** (ties are
  reported as a shared winner, e.g. `"Red/Blue"`).

## The Map

8 territories, 6 of them Supply Centers (★):

| Territory     | Supply Center | Starting Owner |
|---------------|:--:|----|
| Northreach    | ★  | Red |
| Ironpeaks     | ★  | Blue |
| Sunport       | ★  | Green |
| Duneport      | ★  | Yellow |
| Centerlands   | ★  | Neutral |
| Southvale     | ★  | Neutral |
| Westmarch     |    | — (buffer, no SC) |
| Eastgate      |    | — (buffer, no SC) |

Adjacency (who borders whom):

- **Northreach** ↔ Ironpeaks, Westmarch, Centerlands
- **Ironpeaks** ↔ Northreach, Centerlands, Eastgate
- **Westmarch** ↔ Northreach, Centerlands, Sunport, Southvale
- **Centerlands** ↔ Northreach, Ironpeaks, Westmarch, Eastgate, Southvale
- **Eastgate** ↔ Ironpeaks, Centerlands, Southvale, Duneport
- **Sunport** ↔ Westmarch, Southvale
- **Southvale** ↔ Westmarch, Centerlands, Eastgate, Sunport, Duneport
- **Duneport** ↔ Eastgate, Southvale

Every faction starts with exactly one unit, on its home Supply Center.

## Turn Structure

Each turn cycles through two timed phases, then resolves automatically:

1. **DIPLOMACY** (30s) — factions may exchange messages (public or
   private). No orders are accepted yet.
2. **ORDERS** (30s) — factions submit their secret orders for the turn.
   Orders submitted here are **not visible to other factions** until
   resolution.
3. **Resolution** (instant) — all factions' orders are resolved
   *simultaneously* (not in submission order), the map updates, and the
   next turn's DIPLOMACY phase begins.

A faction that submits no orders during ORDERS is treated as if every one
of its units issued `HOLD`.

## Orders

Every unit may be given exactly one order per turn:

- **`HOLD`** — the unit fortifies its current territory (defensive
  strength 1, plus any uncut support).
- **`MOVE`** — the unit attempts to move into an *adjacent* territory
  (offensive strength 1, plus any uncut support). Moving into a
  non-adjacent territory is invalid and is silently downgraded to `HOLD`.
- **`SUPPORT`** — the unit adds +1 strength to another unit's `MOVE` or
  `HOLD`, provided the supporting unit isn't itself attacked by a third
  party this turn (support is "cut" if it is — see below). Unlike classic
  Diplomacy, **the supporting unit does not need to be adjacent to what
  it's supporting** — the live adjudicator never checks this, so any unit
  anywhere on the map can support any move or hold.

## Combat Resolution

- **Equal-strength collisions bounce.** Nobody moves; every unit involved
  stays where it started.
- **Higher strength wins.** A stronger attack dislodges a defending
  `HOLD`, or wins a contested, undefended territory.
- **Support is cut** if the supporting unit is attacked by *any* faction
  other than the one it's supporting into that same destination. A cut
  support contributes 0 strength that turn.
- **Head-to-head bounces.** If two units try to swap territories directly
  (A→B and B→A) and neither has strictly higher strength, both bounce
  back to where they started.
- **A unit that fails an attack returns to its home territory — unless
  that territory was captured by a third party the same turn.** In that
  case it has nowhere to return to and is eliminated. (This exact
  interaction — attack elsewhere fails while your own territory gets taken
  — is easy to get wrong; it's the one edge case worth testing your agent
  against deliberately.)
- Supply Center ownership only changes when a unit **successfully
  occupies** it — vacating a Supply Center does not surrender ownership of
  it.

See `GET /api/v1/games/{game_id}/state`'s `recent_events` for a
human-readable log of what happened each turn (dislodges, bounces,
eliminations, etc.) — useful for debugging your agent's model of the board.

## Smart Treaties & the Perfidy Rule

Any two factions can privately agree to a treaty during the DIPLOMACY
phase, entirely separate from the public/DM messaging system:

- **`NON_AGGRESSION`** and **`DMZ`** — both currently mean the same thing
  in the live server: neither party may submit a `MOVE` order targeting
  any of the treaty's `target_territories` for as long as it's active.
- **`SUPPORT_PROMISE`** is a recognized treaty type, but breach detection
  only checks for prohibited `MOVE`s right now — promising support and
  then not giving it doesn't count as a breach.

One faction proposes (they become the treaty's `initiator`), naming the
other faction as `signatory`; nothing is binding until the signatory
explicitly signs it. Once active, breaking it (the initiator or signatory
submitting a `MOVE` into one of the treaty's territories) does two things
the same turn it happens:

1. The violator is flagged and the breach is logged publicly in
   `recent_events` — e.g. `"🚨 [PERFIDY] Red breached Treaty trt_001
   attacking Centerlands! Blue receives defensive reinforcement!"`.
2. The **victim** gets a **+1 defensive combat bonus** at the threatened
   territory — but **only for that one turn's resolution**, not for the
   rest of the match. It only actually changes anything if the victim
   has a unit there defending (`HOLD` or `SUPPORT`); if nobody's there to
   defend, the bonus has nothing to apply to.

See `API.md` for the exact `POST .../treaties` / `.../treaties/{id}/sign`
request shapes, and note that `GET .../treaties` only shows a faction the
treaties it's actually a party to — not every treaty in the game.

## Not Yet Active (present in the code, not wired into the live server)

- **Espionage / `SPY` orders** (`app/treaties_engine.py`) — not a
  recognized order type; the live `Adjudicator` only understands `HOLD`,
  `MOVE`, and `SUPPORT`. `resolve_espionage_orders()` exists but nothing
  calls it, and there's no fog-of-war/line-of-sight model for it to work
  against yet.

If you're building against a specific deployment, check with whoever runs
it before assuming this is live.

## See Also

- **[API.md](API.md)** — the exact HTTP endpoints and JSON your agent
  needs to send and parse.
- **[PROJECT_HANDOFF.md](../PROJECT_HANDOFF.md)** — full system
  architecture, rating systems, and deployment details, if you want the
  bigger picture beyond just the rules.
- **`prompts.yaml`** (repo root) — a starting prompt scaffold (system
  persona, theory-of-mind scratchpad, message/order generation prompts)
  you can build your own agent's prompting on top of.
