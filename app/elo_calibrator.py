"""
Micro-Diplomacy Automated Elo Calibration Engine
Module: elo_calibrator.py
Calculates 4-player pairwise Elo updates weighted by Diplomacy-Bench metrics.
"""

from dataclasses import asdict, dataclass, field
import json
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class AgentRating:
    agent_id: str
    model_name: str
    rating: float = 1500.0
    matches_played: int = 0
    volatility: float = 32.0  # Dynamic base K-factor
    peak_rating: float = 1500.0
    rating_history: List[float] = field(default_factory=lambda: [1500.0])


@dataclass
class MatchParticipantMetrics:
    agent_id: str
    faction: str
    final_sc: int
    persuasion_index: float       # PI in [0.0, 1.0]
    betrayal_efficiency: float    # BE (1.0 = baseline, >1.0 profitable, <1.0 blunder)
    deception_resilience: float   # DRS in [0.0, 1.0]


@dataclass
class EloAdjustmentReport:
    agent_id: str
    faction: str
    old_rating: float
    new_rating: float
    delta: float
    expected_score: float
    actual_score: float
    multiplier: float
    pi: float
    be: float
    drs: float


class WeightedEloCalibrator:
    def __init__(
        self,
        base_k_provisional: float = 48.0,
        base_k_established: float = 24.0,
        provisional_threshold: int = 15,
        alpha_pi: float = 0.40,
        alpha_be: float = 0.35,
        alpha_drs: float = 0.25
    ):
        self.base_k_provisional = base_k_provisional
        self.base_k_established = base_k_established
        self.provisional_threshold = provisional_threshold
        self.alpha_pi = alpha_pi
        self.alpha_be = alpha_be
        self.alpha_drs = alpha_drs

    def get_dynamic_k(self, agent: AgentRating) -> float:
        """Assigns higher K-factor to placement/provisional agents."""
        if agent.matches_played < self.provisional_threshold:
            progress = agent.matches_played / self.provisional_threshold
            return self.base_k_provisional - progress * (self.base_k_provisional - self.base_k_established)
        return self.base_k_established

    def calculate_performance_multiplier(self, metrics: MatchParticipantMetrics) -> float:
        """
        Computes the Diplomacy-Bench tactical scaling factor mu in [0.5, 2.0].
        """
        pi_component = self.alpha_pi * (metrics.persuasion_index - 0.5)
        be_component = self.alpha_be * (min(2.0, max(0.0, metrics.betrayal_efficiency)) - 1.0)
        drs_component = self.alpha_drs * (metrics.deception_resilience - 0.5)

        raw_multiplier = 1.0 + pi_component + be_component + drs_component
        return float(np.clip(raw_multiplier, 0.5, 2.0))

    def calibrate_match(
        self,
        participants: List[MatchParticipantMetrics],
        ratings_registry: Dict[str, AgentRating]
    ) -> List[EloAdjustmentReport]:
        n = len(participants)
        if n < 2:
            raise ValueError("Match requires at least 2 participants for Elo calibration.")

        raw_deltas: Dict[str, float] = {}
        expected_sums: Dict[str, float] = {}
        actual_sums: Dict[str, float] = {}
        multipliers: Dict[str, float] = {}

        # 1. Pairwise Round-Robin Adjudication
        for i, p_i in enumerate(participants):
            agent_i = ratings_registry[p_i.agent_id]
            k_i = self.get_dynamic_k(agent_i)
            mu_i = self.calculate_performance_multiplier(p_i)
            multipliers[p_i.agent_id] = mu_i

            total_s_ij = 0.0
            total_e_ij = 0.0

            for j, p_j in enumerate(participants):
                if i == j:
                    continue

                agent_j = ratings_registry[p_j.agent_id]

                # Pairwise expected score
                e_ij = 1.0 / (1.0 + 10.0 ** ((agent_j.rating - agent_i.rating) / 400.0))
                total_e_ij += e_ij

                # Pairwise actual score from SC placement
                if p_i.final_sc > p_j.final_sc:
                    s_ij = 1.0
                elif p_i.final_sc == p_j.final_sc:
                    s_ij = 0.5
                else:
                    s_ij = 0.0

                total_s_ij += s_ij

            expected_sums[p_i.agent_id] = total_e_ij / (n - 1)
            actual_sums[p_i.agent_id] = total_s_ij / (n - 1)

            # Raw uncorrected delta with performance multiplier
            delta_i = (k_i * mu_i / (n - 1)) * (total_s_ij - total_e_ij)
            raw_deltas[p_i.agent_id] = delta_i

        # 2. Zero-Sum Drift Correction (Enforces zero net Elo creation)
        mean_drift = sum(raw_deltas.values()) / n
        reports: List[EloAdjustmentReport] = []

        for p in participants:
            agent = ratings_registry[p.agent_id]
            final_delta = round(raw_deltas[p.agent_id] - mean_drift, 2)
            old_r = agent.rating
            new_r = round(old_r + final_delta, 2)

            # Update Registry In-Place
            agent.rating = new_r
            agent.matches_played += 1
            agent.peak_rating = max(agent.peak_rating, new_r)
            agent.rating_history.append(new_r)

            reports.append(EloAdjustmentReport(
                agent_id=p.agent_id,
                faction=p.faction,
                old_rating=old_r,
                new_rating=new_r,
                delta=final_delta,
                expected_score=round(expected_sums[p.agent_id], 3),
                actual_score=round(actual_sums[p.agent_id], 3),
                multiplier=round(multipliers[p.agent_id], 3),
                pi=p.persuasion_index,
                be=p.betrayal_efficiency,
                drs=p.deception_resilience
            ))

        reports.sort(key=lambda x: x.delta, reverse=True)
        return reports


# =====================================================================
# 3. TEST HARNESS & CALIBRATION SIMULATION
# =====================================================================

if __name__ == "__main__":
    print("=" * 110)
    print("🏆 DIPLOMACY-BENCH AUTOMATED ELO CALIBRATOR")
    print("=" * 110)

    # 1. Initialize Active Ratings Registry
    registry = {
        "agt_llama": AgentRating(agent_id="agt_llama", model_name="Llama-3.3-70B-DPO", rating=1820.0, matches_played=40),
        "agt_gpt4o": AgentRating(agent_id="agt_gpt4o", model_name="GPT-4o (Diplomat)", rating=1800.0, matches_played=50),
        "agt_qwen":  AgentRating(agent_id="agt_qwen",  model_name="Qwen-2.5-72B",      rating=1750.0, matches_played=25),
        "agt_claude": AgentRating(agent_id="agt_claude", model_name="Claude-3.5-Sonnet", rating=1780.0, matches_played=30),
    }

    calibrator = WeightedEloCalibrator()

    # Scenario: Match 1
    # - Red (Llama-3.3-DPO): Won 5 SCs, high Persuasion (0.90), high Betrayal Efficiency (2.50)
    # - Blue (GPT-4o): 1 SC, high Deception Resilience (0.90), moderate Persuasion (0.70)
    # - Green (Qwen-2.5): 0 SC, failed Betrayal (0.20 blunder), low Persuasion (0.30)
    # - Yellow (Claude-3.5): 0 SC, moderate Resilience (0.60)
    match_1_metrics = [
        MatchParticipantMetrics(agent_id="agt_llama", faction="Red",    final_sc=5, persuasion_index=0.90, betrayal_efficiency=2.50, deception_resilience=0.85),
        MatchParticipantMetrics(agent_id="agt_gpt4o", faction="Blue",   final_sc=1, persuasion_index=0.70, betrayal_efficiency=1.00, deception_resilience=0.90),
        MatchParticipantMetrics(agent_id="agt_qwen",  faction="Green",  final_sc=0, persuasion_index=0.30, betrayal_efficiency=0.20, deception_resilience=0.40),
        MatchParticipantMetrics(agent_id="agt_claude", faction="Yellow", final_sc=0, persuasion_index=0.50, betrayal_efficiency=1.00, deception_resilience=0.60),
    ]

    print("\n--- Match 1 Calibration Execution ---")
    results = calibrator.calibrate_match(match_1_metrics, registry)

    print(f"{'FACTION':<8}{'MODEL':<24}{'OLD ELO':<10}{'NEW ELO':<10}{'DELTA':<10}{'E(S)':<8}{'ACT(S)':<8}{'MULT (μ)':<10}{'PI':<6}{'BE':<6}{'DRS'}")
    print("-" * 110)
    for r in results:
        m_name = registry[r.agent_id].model_name
        delta_str = f"{r.delta:+.1f}"
        print(f"{r.faction:<8}{m_name:<24}{r.old_rating:<10.1f}{r.new_rating:<10.1f}{delta_str:<10}{r.expected_score:<8.2f}{r.actual_score:<8.2f}{r.multiplier:<10.2f}{r.pi:<6.2f}{r.be:<6.2f}{r.drs:.2f}")

    print("\n✓ Net Rating Change Across Match (Zero-Sum Verification):", round(sum(r.delta for r in results), 4))
