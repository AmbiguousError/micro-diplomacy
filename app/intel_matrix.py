"""
Micro-Diplomacy Intelligence Verification & Deception Matrix
Module: intel_matrix.py
Tracks multi-source scouting reports, cross-examines contradictions,
audits ground-truth when Line-of-Sight clears, and computes Bayesian belief states.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Dict, List, Optional, Set, Tuple


# =====================================================================
# 1. DATA STRUCTURES & INTEL MODELS
# =====================================================================

class IntelStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    CONFIRMED_TRUE = "CONFIRMED_TRUE"
    CONFIRMED_FALSE = "CONFIRMED_FALSE"
    CONTRADICTED = "CONTRADICTED"


@dataclass
class ReconReport:
    turn: int
    source_faction: str
    territory: str
    reported_unit: str             # Faction name or "EMPTY"
    reported_sc_owner: Optional[str] = None
    raw_message: str = ""
    status: IntelStatus = IntelStatus.UNVERIFIED
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%H:%M:%S"))


@dataclass
class ContradictionAlert:
    turn: int
    territory: str
    faction_a: str
    claim_a: str
    faction_b: str
    claim_b: str
    severity: str = "HIGH"         # "HIGH" (Occupied vs Empty / Different Invaders)


@dataclass
class SourceCredibility:
    faction: str
    reports_submitted: int = 0
    verified_accurate: int = 0
    verified_deceptive: int = 0
    contradictions_flagged: int = 0
    credibility_score: float = 0.50  # Range [0.0, 1.0]

    def update_score(self):
        """
        Bayesian-smoothed credibility calculation with asymmetric penalty for deceit:
        Penalizes explicit verified lies at 3x the weight of honest reports.
        """
        alpha = 1.0 + self.verified_accurate
        beta = 1.0 + (3.0 * self.verified_deceptive) + (0.5 * self.contradictions_flagged)
        self.credibility_score = max(0.05, min(0.95, alpha / (alpha + beta)))


@dataclass
class TerritoryBelief:
    territory: str
    most_likely_unit: str          # Faction name or "EMPTY"
    confidence: float              # Range [0.0, 1.0]
    candidate_probabilities: Dict[str, float]
    intel_status: str              # "OWN_LOS", "CONSENSUS", "CONTESTED", "UNEXPLORED"
    contributing_sources: List[str]


# =====================================================================
# 2. INTELLIGENCE VERIFICATION MATRIX ENGINE
# =====================================================================

class IntelligenceVerificationMatrix:
    """
    Ingests scouting reports from remote bots, detects peer contradictions,
    reconciles historical claims against actual Line-of-Sight observations,
    and maintains source credibility ratings.
    """

    def __init__(self, my_faction: str, all_factions: List[str]):
        self.my_faction = my_faction
        self.factions = [f for f in all_factions if f != my_faction]
        
        # Source credibility trackers
        self.sources: Dict[str, SourceCredibility] = {
            f: SourceCredibility(faction=f) for f in self.factions
        }
        
        # turn -> territory -> list of ReconReport
        self.report_ledger: Dict[int, Dict[str, List[ReconReport]]] = {}
        self.active_contradictions: List[ContradictionAlert] = []
        self.historical_audit_log: List[str] = []

    def ingest_recon_report(
        self,
        turn: int,
        source: str,
        territory: str,
        reported_unit: str,
        reported_sc: Optional[str] = None,
        raw_msg: str = ""
    ) -> Optional[ContradictionAlert]:
        """
        Ingests a scout report and runs cross-examination against existing reports for that turn/sector.
        """
        if source == self.my_faction:
            return None

        report = ReconReport(
            turn=turn,
            source_faction=source,
            territory=territory,
            reported_unit=reported_unit,
            reported_sc_owner=reported_sc,
            raw_message=raw_msg
        )

        self.report_ledger.setdefault(turn, {}).setdefault(territory, []).append(report)
        self.sources[source].reports_submitted += 1

        # Check for immediate contradictions with existing reports from other bots for this turn
        existing_reports = self.report_ledger[turn][territory]
        for prev in existing_reports:
            if prev.source_faction != source and prev.reported_unit != reported_unit:
                alert = ContradictionAlert(
                    turn=turn,
                    territory=territory,
                    faction_a=prev.source_faction,
                    claim_a=f"Garrison = {prev.reported_unit}",
                    faction_b=source,
                    claim_b=f"Garrison = {reported_unit}"
                )
                self.active_contradictions.append(alert)
                prev.status = IntelStatus.CONTRADICTED
                report.status = IntelStatus.CONTRADICTED

                self.sources[source].contradictions_flagged += 1
                self.sources[prev.source_faction].contradictions_flagged += 1
                self.sources[source].update_score()
                self.sources[prev.source_faction].update_score()

                log_entry = (
                    f"⚠️ [CONTRADICTION Turn {turn} @ {territory}] "
                    f"{prev.source_faction} claims '{prev.reported_unit}' vs. "
                    f"{source} claims '{reported_unit}'"
                )
                self.historical_audit_log.append(log_entry)
                print(log_entry)
                return alert

        return None

    def audit_ground_truth(self, turn: int, current_map: Dict[str, Any], line_of_sight: Set[str]):
        """
        Audits past and current reports against actual ground truth for all sectors in Line-of-Sight.
        """
        if turn not in self.report_ledger:
            return

        for terr in line_of_sight:
            if terr not in self.report_ledger[turn]:
                continue

            # Ground truth from actual game state
            actual_unit = current_map[terr].get("unit_faction") or "EMPTY"
            reports = self.report_ledger[turn][terr]

            for rep in reports:
                src = self.sources[rep.source_faction]
                if rep.reported_unit == actual_unit:
                    rep.status = IntelStatus.CONFIRMED_TRUE
                    src.verified_accurate += 1
                    src.update_score()
                    log = f"✅ [TRUTH AUDIT Turn {turn}] {rep.source_faction} HONEST: {terr} was indeed '{actual_unit}'"
                else:
                    rep.status = IntelStatus.CONFIRMED_FALSE
                    src.verified_deceptive += 1
                    src.update_score()
                    log = (
                        f"🚨 [DECEPTION AUDIT Turn {turn}] {rep.source_faction} LIED: Claimed {terr} was "
                        f"'{rep.reported_unit}', but actual garrison was '{actual_unit}'"
                    )
                
                self.historical_audit_log.append(log)
                print(log)

    def synthesize_belief_state(
        self,
        turn: int,
        all_territories: List[str],
        current_map: Dict[str, Any],
        line_of_sight: Set[str]
    ) -> Dict[str, TerritoryBelief]:
        """
        Builds a probabilistic consensus model of the entire board by weighting
        claims by their reporting sources' dynamic credibility scores.
        """
        belief_map: Dict[str, TerritoryBelief] = {}
        all_options = ["EMPTY", "Red", "Blue", "Green", "Yellow"]

        for terr in all_territories:
            # 1. Territory is inside our direct Line-of-Sight (100% certainty)
            if terr in line_of_sight:
                actual_unit = current_map[terr].get("unit_faction") or "EMPTY"
                belief_map[terr] = TerritoryBelief(
                    territory=terr,
                    most_likely_unit=actual_unit,
                    confidence=1.0,
                    candidate_probabilities={actual_unit: 1.0},
                    intel_status="OWN_LOS",
                    contributing_sources=[self.my_faction]
                )
                continue

            # 2. Obscured territory - aggregate reports weighted by credibility
            reports = self.report_ledger.get(turn, {}).get(terr, [])
            if not reports:
                belief_map[terr] = TerritoryBelief(
                    territory=terr,
                    most_likely_unit="UNKNOWN",
                    confidence=0.0,
                    candidate_probabilities={opt: 0.20 for opt in all_options},
                    intel_status="UNEXPLORED",
                    contributing_sources=[]
                )
                continue

            weighted_votes: Dict[str, float] = {opt: 0.1 for opt in all_options}  # Prior baseline
            sources_involved = []
            has_contradiction = False

            for rep in reports:
                cred = self.sources[rep.source_faction].credibility_score
                weighted_votes[rep.reported_unit] += cred
                sources_involved.append(rep.source_faction)
                if rep.status == IntelStatus.CONTRADICTED:
                    has_contradiction = True

            total_weight = sum(weighted_votes.values())
            probs = {k: round(v / total_weight, 3) for k, v in weighted_votes.items()}
            top_candidate = max(probs.items(), key=lambda x: x[1])

            belief_map[terr] = TerritoryBelief(
                territory=terr,
                most_likely_unit=top_candidate[0],
                confidence=top_candidate[1],
                candidate_probabilities=probs,
                intel_status="CONTESTED" if has_contradiction else "CONSENSUS",
                contributing_sources=sources_involved
            )

        return belief_map

    def render_intel_prompt_block(
        self,
        turn: int,
        all_territories: List[str],
        current_map: Dict[str, Any],
        line_of_sight: Set[str]
    ) -> str:
        """
        Formats an intelligence telemetry block for prompt injection into the LLM agent.
        """
        beliefs = self.synthesize_belief_state(turn, all_territories, current_map, line_of_sight)

        source_rows = []
        for f, s in self.sources.items():
            source_rows.append(
                f"- **{f}**: Credibility = {s.credibility_score:.2f} "
                f"(Honest: {s.verified_accurate} | Deceptive: {s.verified_deceptive} | Contradictions: {s.contradictions_flagged})"
            )

        belief_rows = []
        for terr, b in beliefs.items():
            if b.intel_status == "OWN_LOS":
                continue  # Skip territories directly visible to save token context
            belief_rows.append(
                f"- **{terr}** [{b.intel_status}]: Likely '{b.most_likely_unit}' (Confidence: {int(b.confidence * 100)}%) "
                f"| Sources: {b.contributing_sources or 'None'} | Dist: {b.candidate_probabilities}"
            )

        contradiction_rows = []
        for c in self.active_contradictions[-4:]:  # Most recent 4
            contradiction_rows.append(
                f"- ⚠️ Turn {c.turn} @ {c.territory}: {c.faction_a} ('{c.claim_a}') vs. {c.faction_b} ('{c.claim_b}')"
            )

        return f"""
### 🛰️ INTELLIGENCE VERIFICATION & CREDIBILITY MATRIX
{chr(10).join(source_rows)}

### 🗺️ FOG-OF-WAR BELIEF STATE ESTIMATES (Obscured Sectors)
{chr(10).join(belief_rows) or "All sectors in direct Line of Sight."}

### ⚠️ ACTIVE RECON CONTRADICTIONS & DECEPTION WARNINGS
{chr(10).join(contradiction_rows) or "No active intelligence contradictions."}
"""


# =====================================================================
# 3. VERIFICATION & SIMULATION TEST HARNESS
# =====================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("🔬 SIMULATING INTEL VERIFICATION MATRIX (Fog-of-War Multi-Agent Cross-Check)")
    print("=" * 80)

    # Initialize Red Faction's matrix against Blue, Green, Yellow
    matrix = IntelligenceVerificationMatrix(
        my_faction="Red",
        all_factions=["Red", "Blue", "Green", "Yellow"]
    )

    all_map_nodes = ["Northreach", "Ironpeaks", "Westmarch", "Centerlands", "Eastgate", "Sunport", "Southvale", "Duneport"]
    red_los_t1 = {"Northreach", "Ironpeaks", "Westmarch", "Centerlands"}

    # Phase 1: Ingest reports from bots about unseen southern sectors
    print("\n--- Phase 1: Ingesting Turn 1 Recon Messages ---")
    matrix.ingest_recon_report(
        turn=1,
        source="Blue",
        territory="Southvale",
        reported_unit="EMPTY",
        raw_msg="Southvale is clear. Move in freely."
    )
    matrix.ingest_recon_report(
        turn=1,
        source="Green",
        territory="Southvale",
        reported_unit="Yellow",
        raw_msg="Warning: Yellow has stationed an army in Southvale."
    )
    matrix.ingest_recon_report(
        turn=1,
        source="Yellow",
        territory="Duneport",
        reported_unit="Yellow",
        raw_msg="I am holding Duneport."
    )

    # Phase 2: Synthesize probabilistic belief state
    current_map_t1 = {
        "Northreach": {"sc_owner": "Red", "unit_faction": "Red"},
        "Ironpeaks": {"sc_owner": "Blue", "unit_faction": "Blue"},
        "Westmarch": {"sc_owner": None, "unit_faction": None},
        "Centerlands": {"sc_owner": "Neutral", "unit_faction": None},
        "Eastgate": {"sc_owner": "FOG_OF_WAR", "unit_faction": "FOG_OF_WAR"},
        "Sunport": {"sc_owner": "FOG_OF_WAR", "unit_faction": "FOG_OF_WAR"},
        "Southvale": {"sc_owner": "FOG_OF_WAR", "unit_faction": "FOG_OF_WAR"},
        "Duneport": {"sc_owner": "FOG_OF_WAR", "unit_faction": "FOG_OF_WAR"},
    }

    prompt_block = matrix.render_intel_prompt_block(
        turn=1,
        all_territories=all_map_nodes,
        current_map=current_map_t1,
        line_of_sight=red_los_t1
    )
    print(prompt_block)

    # Phase 3: Turn 2 Resolution & Ground Truth Audit
    print("\n--- Phase 2: Auditing Historical Truth on Turn 2 ---")
    red_los_t2 = {"Northreach", "Westmarch", "Centerlands", "Southvale", "Sunport", "Duneport"}
    current_map_t2 = {
        "Southvale": {"sc_owner": "Yellow", "unit_faction": "Yellow"},
        "Duneport": {"sc_owner": "Yellow", "unit_faction": "Yellow"},
    }

    matrix.audit_ground_truth(turn=1, current_map=current_map_t2, line_of_sight=red_los_t2)

    print("\n--- Post-Audit Credibility Scores ---")
    for f, s in matrix.sources.items():
        print(f"• {f:<7} -> Credibility: {s.credibility_score:.3f} (Accurate: {s.verified_accurate}, Deceptive: {s.verified_deceptive})")
