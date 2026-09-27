import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel

# =====================================================================
# 1. MAP TOPOLOGY & CONSTANTS
# =====================================================================

FACTIONS = ["Red", "Blue", "Green", "Yellow"]

ADJACENCY: Dict[str, Set[str]] = {
    "Northreach": {"Ironpeaks", "Westmarch", "Centerlands"},
    "Ironpeaks": {"Northreach", "Centerlands", "Eastgate"},
    "Westmarch": {"Northreach", "Centerlands", "Sunport", "Southvale"},
    "Centerlands": {"Northreach", "Ironpeaks", "Westmarch", "Eastgate", "Southvale"},
    "Eastgate": {"Ironpeaks", "Centerlands", "Southvale", "Duneport"},
    "Sunport": {"Westmarch", "Southvale"},
    "Southvale": {"Westmarch", "Centerlands", "Eastgate", "Sunport", "Duneport"},
    "Duneport": {"Eastgate", "Southvale"},
}

SUPPLY_CENTERS: Set[str] = {
    "Northreach", "Ironpeaks", "Centerlands", "Sunport", "Southvale", "Duneport"
}

STARTING_POSITIONS: Dict[str, str] = {
    "Red": "Northreach",
    "Blue": "Ironpeaks",
    "Green": "Sunport",
    "Yellow": "Duneport",
}

WIN_SC_THRESHOLD = 5


@dataclass
class MapTopology:
    """Bundles what used to be three separate module-level globals so a
    GameSession/Adjudicator/SimState can use a per-instance map instead of
    always closing over ADJACENCY/SUPPLY_CENTERS/STARTING_POSITIONS - see
    build_generated_topology() below for the other way to construct one."""
    territories: List[str]
    adjacency: Dict[str, Set[str]]
    supply_centers: Set[str]
    starting_positions: Dict[str, str]
    coordinates: Dict[str, Dict[str, float]] = field(default_factory=dict)


CLASSIC_TOPOLOGY = MapTopology(
    territories=list(ADJACENCY),
    adjacency=ADJACENCY,
    supply_centers=SUPPLY_CENTERS,
    starting_positions=STARTING_POSITIONS,
)


def build_generated_topology() -> MapTopology:
    """Wraps app/map_generator.py's MapGenerator (previously unwired dead
    code - see TODO.md) into a usable MapTopology. Two adaptations needed:
    generate_topology() returns adjacency as lists, not sets, and it has no
    concept of per-faction starting positions at all - both fixed up here
    rather than in map_generator.py itself."""
    from .map_generator import MapGenerator

    raw = MapGenerator().generate_topology()
    adjacency = {terr: set(neighbors) for terr, neighbors in raw["adjacency"].items()}
    supply_centers = set(raw["supply_centers"])
    home_scs = random.sample(sorted(supply_centers), len(FACTIONS))
    starting_positions = dict(zip(FACTIONS, home_scs))
    return MapTopology(
        territories=list(adjacency),
        adjacency=adjacency,
        supply_centers=supply_centers,
        starting_positions=starting_positions,
        coordinates=raw["coordinates"],
    )

# =====================================================================
# 2. DATA MODELS
# =====================================================================

class Phase(str, Enum):
    WAITING = "WAITING"
    DIPLOMACY = "DIPLOMACY"
    ORDERS = "ORDERS"
    RESOLVED = "RESOLVED"
    FINISHED = "FINISHED"

class ActionType(str, Enum):
    HOLD = "HOLD"
    MOVE = "MOVE"
    SUPPORT = "SUPPORT"
    SPY = "SPY"

class Order(BaseModel):
    unit_territory: str
    action: ActionType
    target_destination: Optional[str] = None
    target_faction: Optional[str] = None
    target_source: Optional[str] = None

class TerritoryState(BaseModel):
    sc_owner: Optional[str] = None
    unit_faction: Optional[str] = None

class GameState(BaseModel):
    game_id: str
    turn: int
    phase: Phase
    time_remaining_seconds: int
    map: Dict[str, TerritoryState]
    scores: Dict[str, int]
    winner: Optional[str] = None
    recent_events: List[str] = []
    # LLM-generated caster commentary for the turn that just resolved (see
    # app/dual_caster.py) - text only, no synthesized audio (Piper TTS
    # isn't wired in). Empty if generation hasn't run yet or last failed.
    caster_script: List[Dict[str, str]] = []
    # Non-empty only for practice matches (see POST /api/v1/practice):
    # faction -> archetype class name for every faction controlled by a
    # built-in bot rather than a real registered agent. Exposed publicly
    # so clients can be honest about which opponents are simulated.
    bot_factions: Dict[str, str] = {}
    # "fixed" (the classic 8-territory map, the default and only mode
    # before this field existed) or "generated" (see
    # build_generated_topology() below). adjacency/supply_centers/
    # coordinates describe *this game's own* map - for "fixed" games
    # they're always exactly ADJACENCY/SUPPLY_CENTERS/{} above, but every
    # client should read them from here rather than assuming the classic
    # map, since a "generated" game's topology varies every time.
    map_mode: str = "fixed"
    adjacency: Dict[str, List[str]] = {}
    supply_centers: List[str] = []
    coordinates: Dict[str, Dict[str, float]] = {}
    submitted_orders: Dict[str, List[Dict[str, Any]]] = {}

# =====================================================================
# 3. ADJUDICATION ALGORITHM
# =====================================================================

class Adjudicator:
    @staticmethod
    def adjudicate(
        current_map: Dict[str, TerritoryState],
        submitted_orders: Dict[str, List[Order]],
        defensive_buffs: Optional[Dict[str, Dict[str, int]]] = None,
        topology: MapTopology = CLASSIC_TOPOLOGY,
    ) -> Tuple[Dict[str, TerritoryState], List[str]]:
        """
        defensive_buffs: faction -> territory -> bonus strength, from
        app/treaties_engine.py's TreatyAndEspionageEngine (the "Perfidy
        Rule" +1 defensive bonus after a treaty breach - see
        PROJECT_HANDOFF.md). Applies only to a defending HOLD/SUPPORT-hold
        at that territory, never to an attacking MOVE.

        topology: which map this game is actually playing on (see
        MapTopology/CLASSIC_TOPOLOGY/build_generated_topology() above) -
        defaults to the classic fixed map so every existing caller keeps
        working unchanged.
        """
        defensive_buffs = defensive_buffs or {}
        adjacency = topology.adjacency
        supply_centers = topology.supply_centers
        events: List[str] = []
        new_map: Dict[str, TerritoryState] = {
            t: TerritoryState(sc_owner=state.sc_owner, unit_faction=None)
            for t, state in current_map.items()
        }

        active_orders: Dict[str, Tuple[str, Order]] = {}
        for faction, orders in submitted_orders.items():
            for order in orders:
                terr = order.unit_territory
                if current_map[terr].unit_faction == faction:
                    active_orders[terr] = (faction, order)

        for terr, state in current_map.items():
            if state.unit_faction and terr not in active_orders:
                active_orders[terr] = (
                    state.unit_faction,
                    Order(unit_territory=terr, action=ActionType.HOLD)
                )

        uncut_supports: Set[str] = set()
        for terr, (faction, order) in active_orders.items():
            if order.action == ActionType.SUPPORT:
                dest = order.target_destination
                is_cut = False
                for other_terr, (_, other_order) in active_orders.items():
                    if (
                        other_order.action == ActionType.MOVE
                        and other_order.target_destination == terr
                        and other_terr != dest
                    ):
                        is_cut = True
                        events.append(f"Support from {terr} was CUT by attack from {other_terr}.")
                        break
                if not is_cut:
                    uncut_supports.add(terr)

        incoming_attacks: Dict[str, List[Tuple[str, str, int]]] = {t: [] for t in adjacency}
        holds: Dict[str, Tuple[str, int]] = {}

        for terr, (faction, order) in active_orders.items():
            if order.action == ActionType.MOVE:
                dest = order.target_destination
                if dest in adjacency.get(terr, set()):
                    support_bonus = sum(
                        1 for s_terr in uncut_supports
                        if active_orders[s_terr][1].target_source == terr
                        and active_orders[s_terr][1].target_destination == dest
                    )
                    incoming_attacks[dest].append((terr, faction, 1 + support_bonus))
                else:
                    events.append(f"Invalid move: {terr} is not adjacent to {dest}. Defaulted to HOLD.")
                    buff = defensive_buffs.get(faction, {}).get(terr, 0)
                    holds[terr] = (faction, 1 + buff)

            elif order.action in (ActionType.HOLD, ActionType.SUPPORT, ActionType.SPY):
                support_bonus = sum(
                    1 for s_terr in uncut_supports
                    if active_orders[s_terr][1].target_source == terr
                    and active_orders[s_terr][1].target_destination == terr
                )
                buff = defensive_buffs.get(faction, {}).get(terr, 0)
                if buff:
                    events.append(f"{faction}'s defense at {terr} includes a +{buff} Perfidy bonus from a treaty breach.")
                holds[terr] = (faction, 1 + support_bonus + buff)

        # Two separate maps, merged after the loop below, rather than one
        # shared dict written from both "sides" of a resolution: dest_occupant
        # says who wins a territory as an attack/hold target; origin_bounce_back
        # says which failed attacker tries to return to the territory it left.
        # A single shared dict let a later iteration's bounce-back silently
        # overwrite an earlier iteration's legitimate dest_occupant result for
        # the same territory (e.g. a unit's home being captured by a third
        # party the same turn it attacks elsewhere and fails), erasing the
        # successful mover with no elimination event logged. Merging with
        # dest_occupant taking priority matches standard Diplomacy: a failed
        # attacker only returns home if nothing else took that square.
        dest_occupant: Dict[str, str] = {}
        origin_bounce_back: Dict[str, str] = {}

        for dest in adjacency:
            attacks = incoming_attacks[dest]
            has_holder = dest in holds

            if not attacks:
                if has_holder:
                    dest_occupant[dest] = holds[dest][0]
                continue

            attacks.sort(key=lambda x: x[2], reverse=True)
            max_attack_str = attacks[0][2]
            tied_attacks = [atk for atk in attacks if atk[2] == max_attack_str]

            if len(tied_attacks) > 1:
                events.append(f"Attack bounce at {dest}: Multiple forces collided with strength {max_attack_str}.")
                if has_holder:
                    dest_occupant[dest] = holds[dest][0]
                for atk_terr, atk_faction, _ in attacks:
                    origin_bounce_back[atk_terr] = atk_faction
                continue

            winner_terr, winner_faction, win_str = attacks[0]
            head_to_head_fail = False
            if active_orders.get(dest, (None, None))[1]:
                dest_order = active_orders[dest][1]
                if dest_order.action == ActionType.MOVE and dest_order.target_destination == winner_terr:
                    opp_attacks = [a for a in incoming_attacks[winner_terr] if a[0] == dest]
                    if opp_attacks:
                        opp_str = opp_attacks[0][2]
                        if win_str <= opp_str:
                            head_to_head_fail = True
                            events.append(f"Head-to-head bounce between {winner_terr} and {dest}.")
                            origin_bounce_back[winner_terr] = winner_faction
                            origin_bounce_back[dest] = active_orders[dest][0]

            if head_to_head_fail:
                continue

            if has_holder:
                def_faction, def_str = holds[dest]
                if win_str > def_str:
                    events.append(f"{winner_faction} dislodged {def_faction} at {dest} ({win_str} vs {def_str}).")
                    dest_occupant[dest] = winner_faction
                else:
                    events.append(f"{def_faction} held {dest} against {winner_faction} ({def_str} vs {win_str}).")
                    dest_occupant[dest] = def_faction
                    origin_bounce_back[winner_terr] = winner_faction
            else:
                events.append(f"{winner_faction} moved from {winner_terr} to {dest} successfully.")
                dest_occupant[dest] = winner_faction

        surviving_units: Dict[str, str] = dict(dest_occupant)
        for origin_terr, faction in origin_bounce_back.items():
            if origin_terr in surviving_units:
                events.append(
                    f"{faction} was eliminated: home territory {origin_terr} was captured while its unit was away attacking."
                )
            else:
                surviving_units[origin_terr] = faction

        for terr, faction in surviving_units.items():
            new_map[terr].unit_faction = faction
            if terr in supply_centers:
                new_map[terr].sc_owner = faction

        return new_map, events


# =====================================================================
# 4. LIGHTWEIGHT SIMULATION STATE (used by the Gauntlet harness & archetypes)
# =====================================================================

@dataclass
class SimState:
    """
    Flat, dependency-free game state for running isolated simulations
    (gauntlet calibration, MCTS rollouts) without a full GameSession.
    """
    turn: int
    map_units: Dict[str, str] = field(default_factory=dict)  # territory -> controlling faction
    map_sc: Dict[str, str] = field(default_factory=dict)     # territory -> SC owner faction or "Neutral"
    topology: MapTopology = field(default_factory=lambda: CLASSIC_TOPOLOGY)

    def get_scores(self) -> Dict[str, int]:
        scores = {f: 0 for f in FACTIONS}
        for owner in self.map_sc.values():
            if owner in scores:
                scores[owner] += 1
        return scores

    def is_terminal(self) -> Tuple[bool, Optional[str]]:
        scores = self.get_scores()
        for faction, sc_count in scores.items():
            if sc_count >= WIN_SC_THRESHOLD:
                return True, faction
        if self.turn >= 10:
            top_score = max(scores.values())
            winners = [f for f, s in scores.items() if s == top_score]
            return True, "/".join(winners)
        return False, None

    @classmethod
    def from_territory_map(
        cls,
        territory_map: Dict[str, "TerritoryState"],
        turn: int,
        topology: MapTopology = CLASSIC_TOPOLOGY,
    ) -> "SimState":
        """The inverse of FastAdjudicator.step()'s internal conversion - lets
        code holding a full GameSession's map (app/main.py) query an
        archetype bot (app/archetypes.py), which only knows how to read a
        SimState, without needing its own copy of this conversion."""
        map_units = {t: ts.unit_faction for t, ts in territory_map.items() if ts.unit_faction}
        map_sc = {t: (ts.sc_owner or "Neutral") for t, ts in territory_map.items() if t in topology.supply_centers}
        return cls(turn=turn, map_units=map_units, map_sc=map_sc, topology=topology)


class FastAdjudicator:
    """Thin SimState-shaped wrapper around Adjudicator.adjudicate()."""

    @staticmethod
    def step(
        state: SimState,
        joint_orders: Dict[str, Tuple[Order, ...]],
        defensive_buffs: Optional[Dict[str, Dict[str, int]]] = None,
    ) -> SimState:
        topology = state.topology
        current_map: Dict[str, TerritoryState] = {}
        for terr in topology.adjacency:
            unit = state.map_units.get(terr)
            sc_owner = state.map_sc.get(terr) if terr in topology.supply_centers else None
            current_map[terr] = TerritoryState(
                sc_owner=None if sc_owner in (None, "Neutral") else sc_owner,
                unit_faction=None if unit in (None, "Neutral") else unit,
            )

        submitted_orders = {faction: list(orders) for faction, orders in joint_orders.items()}
        new_map, _events = Adjudicator.adjudicate(
            current_map, submitted_orders, defensive_buffs=defensive_buffs, topology=topology
        )

        new_map_units = {terr: ts.unit_faction for terr, ts in new_map.items() if ts.unit_faction}
        new_map_sc = {terr: (ts.sc_owner or "Neutral") for terr, ts in new_map.items() if terr in topology.supply_centers}

        return SimState(turn=state.turn + 1, map_units=new_map_units, map_sc=new_map_sc, topology=topology)
