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

# =====================================================================
# 3. ADJUDICATION ALGORITHM
# =====================================================================

class Adjudicator:
    @staticmethod
    def adjudicate(
        current_map: Dict[str, TerritoryState],
        submitted_orders: Dict[str, List[Order]]
    ) -> Tuple[Dict[str, TerritoryState], List[str]]:
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

        incoming_attacks: Dict[str, List[Tuple[str, str, int]]] = {t: [] for t in ADJACENCY}
        holds: Dict[str, Tuple[str, int]] = {}

        for terr, (faction, order) in active_orders.items():
            if order.action == ActionType.MOVE:
                dest = order.target_destination
                if dest in ADJACENCY.get(terr, set()):
                    support_bonus = sum(
                        1 for s_terr in uncut_supports
                        if active_orders[s_terr][1].target_source == terr
                        and active_orders[s_terr][1].target_destination == dest
                    )
                    incoming_attacks[dest].append((terr, faction, 1 + support_bonus))
                else:
                    events.append(f"Invalid move: {terr} is not adjacent to {dest}. Defaulted to HOLD.")
                    holds[terr] = (faction, 1)

            elif order.action in (ActionType.HOLD, ActionType.SUPPORT):
                support_bonus = sum(
                    1 for s_terr in uncut_supports
                    if active_orders[s_terr][1].target_source == terr
                    and active_orders[s_terr][1].target_destination == terr
                )
                holds[terr] = (faction, 1 + support_bonus)

        surviving_units: Dict[str, str] = {}

        for dest in ADJACENCY:
            attacks = incoming_attacks[dest]
            has_holder = dest in holds

            if not attacks:
                if has_holder:
                    surviving_units[dest] = holds[dest][0]
                continue

            attacks.sort(key=lambda x: x[2], reverse=True)
            max_attack_str = attacks[0][2]
            tied_attacks = [atk for atk in attacks if atk[2] == max_attack_str]

            if len(tied_attacks) > 1:
                events.append(f"Attack bounce at {dest}: Multiple forces collided with strength {max_attack_str}.")
                if has_holder:
                    surviving_units[dest] = holds[dest][0]
                for atk_terr, _, _ in attacks:
                    surviving_units[atk_terr] = active_orders[atk_terr][0]
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
                            surviving_units[winner_terr] = winner_faction
                            surviving_units[dest] = active_orders[dest][0]

            if head_to_head_fail:
                continue

            if has_holder:
                def_faction, def_str = holds[dest]
                if win_str > def_str:
                    events.append(f"{winner_faction} dislodged {def_faction} at {dest} ({win_str} vs {def_str}).")
                    surviving_units[dest] = winner_faction
                else:
                    events.append(f"{def_faction} held {dest} against {winner_faction} ({def_str} vs {win_str}).")
                    surviving_units[dest] = def_faction
                    surviving_units[winner_terr] = winner_faction
            else:
                events.append(f"{winner_faction} moved from {winner_terr} to {dest} successfully.")
                surviving_units[dest] = winner_faction

        for terr, faction in surviving_units.items():
            new_map[terr].unit_faction = faction
            if terr in SUPPLY_CENTERS:
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


class FastAdjudicator:
    """Thin SimState-shaped wrapper around Adjudicator.adjudicate()."""

    @staticmethod
    def step(state: SimState, joint_orders: Dict[str, Tuple[Order, ...]]) -> SimState:
        current_map: Dict[str, TerritoryState] = {}
        for terr in ADJACENCY:
            unit = state.map_units.get(terr)
            sc_owner = state.map_sc.get(terr) if terr in SUPPLY_CENTERS else None
            current_map[terr] = TerritoryState(
                sc_owner=None if sc_owner in (None, "Neutral") else sc_owner,
                unit_faction=None if unit in (None, "Neutral") else unit,
            )

        submitted_orders = {faction: list(orders) for faction, orders in joint_orders.items()}
        new_map, _events = Adjudicator.adjudicate(current_map, submitted_orders)

        new_map_units = {terr: ts.unit_faction for terr, ts in new_map.items() if ts.unit_faction}
        new_map_sc = {terr: (ts.sc_owner or "Neutral") for terr, ts in new_map.items() if terr in SUPPLY_CENTERS}

        return SimState(turn=state.turn + 1, map_units=new_map_units, map_sc=new_map_sc)
