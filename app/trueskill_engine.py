"""
Micro-Diplomacy TrueSkill 2 Bayesian MMR Engine
Implements Gaussian Belief Propagation for 4-Player FFA with Diplomacy-Bench Modulators.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Tuple
import numpy as np


@dataclass
class TrueSkillProfile:
    agent_id: str
    mu: float = 25.0           # Prior mean
    sigma: float = 8.333       # Prior standard deviation (uncertainty)
    matches_played: int = 0
    conservative_mmr: int = 0  # max(0, round((mu - 3*sigma) * 100))

    def update_mmr(self):
        self.conservative_mmr = max(0, int(round((self.mu - (3.0 * self.sigma)) * 100)))


@dataclass
class MatchResultSnapshot:
    agent_id: str
    placement_rank: int        # 1 (Winner) to 4 (Last)
    final_sc: int
    persuasion_index: float    # PI [0.0, 1.0]
    betrayal_efficiency: float # BE [0.0, 3.0]
    deception_resilience: float# DRS [0.0, 1.0]


class BayesianMMREngine:
    def __init__(self, beta: float = 4.167, tau: float = 0.083):
        self.beta = beta           # Performance variance
        self.tau = tau             # Dynamic additive volatility per match
        self.beta_sq = beta ** 2

    def _v_exceedance(self, t: float, eps: float = 0.0) -> float:
        """Gaussian truncated mean correction."""
        denom = max(1e-7, 1.0 - self._erf_cdf(t))
        return self._gaussian_pdf(t) / denom

    def _w_exceedance(self, t: float, eps: float = 0.0) -> float:
        """Gaussian truncated variance correction."""
        v = self._v_exceedance(t, eps)
        return v * (v - t)

    @staticmethod
    def _gaussian_pdf(x: float) -> float:
        return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * (x ** 2))

    @staticmethod
    def _erf_cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def update_match_ratings(
        self,
        participants: List[MatchResultSnapshot],
        registry: Dict[str, TrueSkillProfile]
    ) -> List[Dict[str, Any]]:
        """
        Executes a 4-player ranking update using Gaussian message passing.
        Incorporates Diplomacy-Bench multipliers to accelerate convergence.
        """
        # Sort by placement ascending (1st place first)
        ordered = sorted(participants, key=lambda p: p.placement_rank)
        n = len(ordered)

        delta_mu: Dict[str, float] = {p.agent_id: 0.0 for p in ordered}
        delta_sigma_sq: Dict[str, float] = {p.agent_id: 0.0 for p in ordered}

        # Pairwise comparison between adjacent rank positions (i vs i+1)
        for i in range(n - 1):
            p_win = ordered[i]
            p_los = ordered[i + 1]

            prof_win = registry[p_win.agent_id]
            prof_los = registry[p_los.agent_id]

            # Inflate uncertainty by additive match dynamics (tau)
            sig_win_sq = (prof_win.sigma ** 2) + (self.tau ** 2)
            sig_los_sq = (prof_los.sigma ** 2) + (self.tau ** 2)

            c = math.sqrt((2.0 * self.beta_sq) + sig_win_sq + sig_los_sq)
            diff = (prof_win.mu - prof_los.mu) / c

            v = self._v_exceedance(diff)
            w = self._w_exceedance(diff)

            # Diplomacy-Bench performance weight multiplier
            perf_factor = 1.0 + (0.3 * (p_win.persuasion_index - 0.5)) + (0.2 * (p_win.betrayal_efficiency - 1.0))
            perf_factor = max(0.6, min(1.8, perf_factor))

            # Mean shifts
            d_mu_win = (sig_win_sq / c) * v * perf_factor
            d_mu_los = -(sig_los_sq / c) * v * perf_factor

            # Variance shrinkages
            d_sig_win = (sig_win_sq / (c ** 2)) * w
            d_sig_los = (sig_los_sq / (c ** 2)) * w

            delta_mu[p_win.agent_id] += d_mu_win
            delta_mu[p_los.agent_id] += d_mu_los
            delta_sigma_sq[p_win.agent_id] += d_sig_win
            delta_sigma_sq[p_los.agent_id] += d_sig_los

        # Apply computed updates to registry
        reports = []
        for p in ordered:
            prof = registry[p.agent_id]
            old_mmr = prof.conservative_mmr

            prof.mu += delta_mu[p.agent_id]
            
            # Update variance with floor protection
            current_var = (prof.sigma ** 2) + (self.tau ** 2)
            new_var = max(0.8, current_var * (1.0 - min(0.9, delta_sigma_sq[p.agent_id])))
            prof.sigma = math.sqrt(new_var)
            prof.matches_played += 1
            prof.update_mmr()

            reports.append({
                "agent_id": p.agent_id,
                "placement": p.placement_rank,
                "old_mmr": old_mmr,
                "new_mmr": prof.conservative_mmr,
                "mu": round(prof.mu, 3),
                "sigma": round(prof.sigma, 3),
                "delta": prof.conservative_mmr - old_mmr
            })

        return reports
