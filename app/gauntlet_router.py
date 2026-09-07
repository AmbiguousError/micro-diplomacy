from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from .gauntlet_runner import GauntletHarness
from .mcts import Order

router = APIRouter(prefix="/api/v1/gauntlet", tags=["Gauntlet Qualification"])
harness = GauntletHarness()

class GauntletResponse(BaseModel):
    passed: bool
    calibrated_mmr: int
    qualifying_tier: str
    syntax_errors: int
    diagnostics: List[str]

@router.post("/calibrate/{agent_id}", response_model=GauntletResponse)
async def run_gauntlet(agent_id: str):
    """
    Executes an isolated 4-match battery against built-in archetypes
    to assign an initial MMR and verify format compliance.
    """
    # Simple default hold policy for simulation testing
    def mock_agent_policy(turn: int, map_units: dict) -> List[Order]:
        return [Order(unit_territory=k, action="HOLD") for k, v in map_units.items() if v == "Red"]

    result = harness.run_calibration_suite(
        candidate_agent_id=agent_id,
        candidate_order_fn=mock_agent_policy
    )

    if not result.passed and result.syntax_errors > 0:
        raise HTTPException(
            status_code=422,
            detail=f"Gauntlet verification failed with {result.syntax_errors} syntax errors."
        )

    return GauntletResponse(
        passed=result.passed,
        calibrated_mmr=result.final_mmr,
        qualifying_tier=result.qualifying_tier,
        syntax_errors=result.syntax_errors,
        diagnostics=result.diagnostic_notes
    )
