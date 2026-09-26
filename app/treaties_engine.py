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

    def to_dict(self) -> Dict[str, Any]:
        """Serializes to a JSON-safe dict (see app/main.py's GameSession
        persistence - SmartTreaty is a plain dataclass, not pydantic, so
        this can't just be model_dump()'d like Order/Message elsewhere)."""
        return {
            "active_treaties": {
                tid: {
                    "treaty_id": t.treaty_id,
                    "initiator": t.initiator,
                    "signatory": t.signatory,
                    "treaty_type": t.treaty_type.value,
                    "target_territories": t.target_territories,
                    "start_turn": t.start_turn,
                    "duration_turns": t.duration_turns,
                    "status": t.status.value,
                    "breached_by": t.breached_by,
                    "signature_hash": t.signature_hash,
                }
                for tid, t in self.active_treaties.items()
            },
            "perfidious_factions": list(self.perfidious_factions),
            "defensive_buffs": self.defensive_buffs,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TreatyAndEspionageEngine":
        engine = cls()
        for tid, td in data.get("active_treaties", {}).items():
            engine.active_treaties[tid] = SmartTreaty(
                treaty_id=td["treaty_id"],
                initiator=td["initiator"],
                signatory=td["signatory"],
                treaty_type=TreatyType(td["treaty_type"]),
                target_territories=td["target_territories"],
                start_turn=td["start_turn"],
                duration_turns=td["duration_turns"],
                status=TreatyStatus(td["status"]),
                breached_by=td.get("breached_by"),
                signature_hash=td.get("signature_hash", ""),
            )
        engine.perfidious_factions = set(data.get("perfidious_factions", []))
        engine.defensive_buffs = data.get("defensive_buffs", {})
        return engine

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
        # Reset each turn: PROJECT_HANDOFF.md describes the bonus as applying
        # "during the subsequent resolution" (i.e. one turn), not
        # permanently. Without this, a buff set here would never be
        # cleared and would silently keep applying to every future turn's
        # combat at that territory, for the rest of the match.
        self.defensive_buffs = {}

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
        turn_messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Resolves SPY commands, returning secret intel packets to spying players.

        A SPY order (unit_territory=<spying unit>, action=SPY,
        target_faction=<faction to investigate>) forfeits that unit's move
        for the turn (it still defends its own territory - see
        Adjudicator.adjudicate()'s HOLD/SUPPORT/SPY bucket) in exchange for
        two things about target_faction, for this turn only:
        - every MOVE order they actually submitted (their real troop
          movements are otherwise never visible - orders are hidden from
          everyone until the whole turn resolves).
        - the content of every private (non-PUBLIC) DM this turn where
          target_faction is the sender or recipient and the spying faction
          wasn't already a party to it (those are already visible via the
          normal GET .../messages endpoint).
        """
        intel_packets = []

        for faction, orders in orders_by_faction.items():
            for order in orders:
                if order.get("action") != "SPY":
                    continue
                target = order.get("target_faction")
                spying_unit = order.get("unit_territory")
                if not target or target == faction:
                    continue

                observed_movements = [
                    f"{target} moved {o.get('unit_territory')} -> {o.get('target_destination')}"
                    for o in orders_by_faction.get(target, [])
                    if o.get("action") == "MOVE"
                ]

                intercepted = [
                    f"{m['sender']} -> {m['recipient']}: '{m['content']}'"
                    for m in turn_messages
                    if m.get("turn") == current_turn
                    and m.get("recipient") != "PUBLIC"
                    and target in (m.get("sender"), m.get("recipient"))
                    and faction not in (m.get("sender"), m.get("recipient"))
                ]

                intel_packets.append({
                    "turn": current_turn,
                    "spying_faction": faction,
                    "source_territory": spying_unit,
                    "target_faction": target,
                    "observed_movements": observed_movements,
                    "intercepted_messages": intercepted,
                })

        return intel_packets
