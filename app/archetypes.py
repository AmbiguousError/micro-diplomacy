"""
Micro-Diplomacy Canonical Baseline Archetypes
Used for the automated Gauntlet qualification and baseline calibration.
"""

from dataclasses import dataclass
import random
from typing import Dict, List
from .mcts import ADJACENCY, Order, SUPPLY_CENTERS, SimState


class BaseArchetype:
    def __init__(self, faction: str):
        self.faction = faction

    def generate_orders(self, turn: int, state: SimState) -> List[Order]:
        raise NotImplementedError

    def generate_messages(self, turn: int, state: SimState) -> List[Dict[str, str]]:
        return []


class PacifistTurtle(BaseArchetype):
    """Never attacks unprovoked. Holds all positions and proposes NAPs."""
    def generate_orders(self, turn: int, state: SimState) -> List[Order]:
        my_units = [terr for terr, owner in state.map_units.items() if owner == self.faction]
        return [Order(unit_territory=u, action="HOLD") for u in my_units]

    def generate_messages(self, turn: int, state: SimState) -> List[Dict[str, str]]:
        return [{"recipient": "PUBLIC", "content": "I seek peace on all borders and will only defend."}]


class OpportunisticGreedy(BaseArchetype):
    """Greedily rushes adjacent Supply Centers regardless of borders."""
    def generate_orders(self, turn: int, state: SimState) -> List[Order]:
        my_units = [terr for terr, owner in state.map_units.items() if owner == self.faction]
        orders = []
        for u in my_units:
            neighbors = list(ADJACENCY.get(u, []))
            unclaimed_scs = [n for n in neighbors if n in SUPPLY_CENTERS and state.map_sc.get(n) != self.faction]
            if unclaimed_scs:
                orders.append(Order(unit_territory=u, action="MOVE", target_destination=random.choice(unclaimed_scs)))
            elif neighbors:
                orders.append(Order(unit_territory=u, action="MOVE", target_destination=random.choice(neighbors)))
            else:
                orders.append(Order(unit_territory=u, action="HOLD"))
        return orders


class MachiavellianTraitor(BaseArchetype):
    """Offers support in chat on Turns 1-2, then executes a deterministic backstab on Turn 3."""
    def generate_orders(self, turn: int, state: SimState) -> List[Order]:
        my_units = [terr for terr, owner in state.map_units.items() if owner == self.faction]
        orders = []
        for u in my_units:
            neighbors = list(ADJACENCY.get(u, []))
            if turn < 3:
                # Play passively while building trust
                orders.append(Order(unit_territory=u, action="HOLD"))
            else:
                # Sudden coordinated blitz into highest value neighbor
                targets = [n for n in neighbors if state.map_units.get(n) not in (None, self.faction)]
                if targets:
                    orders.append(Order(unit_territory=u, action="MOVE", target_destination=targets[0]))
                else:
                    orders.append(Order(unit_territory=u, action="MOVE", target_destination=neighbors[0]))
        return orders

    def generate_messages(self, turn: int, state: SimState) -> List[Dict[str, str]]:
        if turn < 3:
            return [{"recipient": "PUBLIC", "content": "Let us maintain our pacts. I will support your expansions."}]
        return [{"recipient": "PUBLIC", "content": "Calculated realignment. Nothing personal."}]


class StochasticChaos(BaseArchetype):
    """Uniform random legal move generator. Tests an agent's resilience to irrational noise."""
    def generate_orders(self, turn: int, state: SimState) -> List[Order]:
        my_units = [terr for terr, owner in state.map_units.items() if owner == self.faction]
        orders = []
        for u in my_units:
            action = random.choice(["HOLD", "MOVE"])
            neighbors = list(ADJACENCY.get(u, []))
            if action == "MOVE" and neighbors:
                orders.append(Order(unit_territory=u, action="MOVE", target_destination=random.choice(neighbors)))
            else:
                orders.append(Order(unit_territory=u, action="HOLD"))
        return orders
