"""
Micro-Diplomacy Smart Treaties & Espionage Module
Handles signed pacts, treaty violation detection, and special combat bonuses.
"""

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple


class TreatyType(str, Enum):
    NON_AGGRESSION = "NON_AGGRESSION"
    DMZ = "DMZ"
    SUPPORT_PROMISE = "SUPPORT_PROMISE"


class TreatyStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    FULFILLED = "FULFILLED"
    BREACHED = "BREACHED"


@dataclass
class SmartTreaty:
    treaty_id: str
    initiator: str
    signatory: str
    treaty_type: TreatyType
    target_territories: List[str]
    start_turn: int
    duration_turns: int
    status: TreatyStatus = TreatyStatus.PENDING
    breached_by: Optional[str] = None
    signature_hash: str = ""

    def generate_hash(self) -> str:
        payload = f"{self.initiator}-{self.signatory}-{self.treaty_type}-{self.start_turn}-{self.duration_turns}"
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


class TreatyAndEspionageEngine:
    def __init__(self):
        self.active_treaties: Dict[str, SmartTreaty] = {}
        self.perfidious_factions: Set[str] = set()
        # Track turn-based defensive buffs: faction -> territory -> bonus strength
        self.defensive_buffs: Dict[str, Dict[str, int]] = {}

    def propose_treaty(
        self,
        initiator: str,
        signatory: str,
        treaty_type: TreatyType,
        territories: List[str],
        current_turn: int,
        duration: int
    ) -> SmartTreaty:
        treaty = SmartTreaty(
            treaty_id=f"trt_{len(self.active_treaties) + 1:03d}",
            initiator=initiator,
            signatory=signatory,
            treaty_type=treaty_type,
            target_territories=territories,
            start_turn=current_turn,
            duration_turns=duration,
            status=TreatyStatus.PENDING
        )
        treaty.signature_hash = treaty.generate_hash()
        self.active_treaties[treaty.treaty_id] = treaty
        return treaty

    def sign_treaty(self, treaty_id: str, faction: str) -> bool:
        treaty = self.active_treaties.get(treaty_id)
        if treaty and treaty.signatory == faction and treaty.status == TreatyStatus.PENDING:
            treaty.status = TreatyStatus.ACTIVE
            return True
        return False

    def evaluate_orders_for_breaches(
        self,
        current_turn: int,
        orders_by_faction: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Audits all submitted orders against active treaties before combat adjudication.
        Applies defensive buffs to victims if a breach is detected.
        """
        breach_events = []

        for t_id, treaty in list(self.active_treaties.items()):
            if treaty.status != TreatyStatus.ACTIVE:
                continue

            # Check expiration
            if current_turn >= treaty.start_turn + treaty.duration_turns:
                treaty.status = TreatyStatus.FULFILLED
                continue

            parties = [treaty.initiator, treaty.signatory]

            for faction in parties:
                target_victim = treaty.signatory if faction == treaty.initiator else treaty.initiator
                orders = orders_by_faction.get(faction, [])

                for order in orders:
                    action = order.get("action")
                    dest = order.get("target_destination")

                    is_breach = False

                    # 1. Check Non-Aggression Pact Violation
                    if treaty.treaty_type == TreatyType.NON_AGGRESSION:
                        if action == "MOVE" and dest in treaty.target_territories:
                            is_breach = True

                    # 2. Check DMZ Violation
                    elif treaty.treaty_type == TreatyType.DMZ:
                        if action == "MOVE" and dest in treaty.target_territories:
                            is_breach = True

                    if is_breach:
                        treaty.status = TreatyStatus.BREACHED
                        treaty.breached_by = faction
                        self.perfidious_factions.add(faction)

                        # Grant victim +1 defensive combat buffer in threatened sectors
                        self.defensive_buffs.setdefault(target_victim, {})
                        self.defensive_buffs[target_victim][dest] = 1

                        breach_events.append({
                            "type": "TREATY_BREACH",
                            "treaty_id": treaty.treaty_id,
                            "violator": faction,
                            "victim": target_victim,
                            "territory": dest,
                            "message": f"🚨 [PERFIDY] {faction} breached Treaty {treaty.treaty_id} attacking {dest}! {target_victim} receives defensive reinforcement!"
                        })
                        break

        return breach_events

    def resolve_espionage_orders(
        self,
        current_turn: int,
        orders_by_faction: Dict[str, List[Dict[str, Any]]],
        intercepted_dms: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Resolves SPY commands, returning secret intel packets to spying players."""
        intel_packets = []

        for faction, orders in orders_by_faction.items():
            for order in orders:
                if order.get("action") == "SPY":
                    target = order.get("target_destination")
                    spying_unit = order.get("unit_territory")

                    # Extract all movements heading into the spied territory
                    incoming_moves = []
                    for other_fac, other_orders in orders_by_faction.items():
                        if other_fac == faction:
                            continue
                        for o in other_orders:
                            if o.get("action") == "MOVE" and o.get("target_destination") == target:
                                incoming_moves.append(f"{other_fac} moving from {o.get('unit_territory')}")

                    # Intercept relevant DMs
                    leaked_msg = None
                    for dm in intercepted_dms:
                        if target in dm.get("content", "") or dm.get("recipient") == target:
                            leaked_msg = f"{dm.get('sender')} -> {dm.get('recipient')}: '{dm.get('content')}'"
                            break

                    intel_packets.append({
                        "spying_faction": faction,
                        "source_territory": spying_unit,
                        "target_territory": target,
                        "observed_incoming_movements": incoming_moves,
                        "intercepted_comms": leaked_msg or "No signals intercepted."
                    })

        return intel_packets
