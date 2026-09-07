import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import httpx
from .gauntlet_runner import GauntletHarness
from .mcts import Order

router = APIRouter(prefix="/api/v1/gauntlet", tags=["Gauntlet Qualification"])
harness = GauntletHarness()

CALLBACK_TIMEOUT_SECONDS = 10.0


class GauntletRequest(BaseModel):
    # The candidate's own HTTP endpoint. Called once per simulated turn with
    # {"turn": <int>, "map_units": {<territory>: <faction or null>}} and
    # expected to respond with {"orders": [{"unit_territory": ..., "action":
    # ..., "target_destination": ...}, ...]} - same order shape as
    # POST /api/v1/games/{game_id}/orders. Matches are simulated instantly
    # (no real-time phase timers), so this is called back-to-back, fast.
    callback_url: str


class GauntletResponse(BaseModel):
    passed: bool
    calibrated_mmr: int
    qualifying_tier: str
    syntax_errors: int
    diagnostics: List[str]


def _make_callback_policy(callback_url: str):
    client = httpx.Client(timeout=CALLBACK_TIMEOUT_SECONDS)

    def candidate_order_fn(turn: int, map_units: Dict[str, Any]) -> List[Order]:
        response = client.post(callback_url, json={"turn": turn, "map_units": map_units})
        response.raise_for_status()
        payload = response.json()
        return [Order(**o) for o in payload.get("orders", [])]

    return candidate_order_fn


@router.post("/calibrate/{agent_id}", response_model=GauntletResponse)
async def run_gauntlet(agent_id: str, request: GauntletRequest):
    """
    Executes an isolated 4-match battery against built-in archetypes to
    assign an initial MMR and verify format compliance. Your agent's
    decision logic is queried via HTTP callback (see GauntletRequest) so it
    can run anywhere, per the project's Bring-Your-Own-Compute model - the
    matches themselves are simulated instantly, not played in real time.
    Any callback failure (timeout, non-2xx, malformed orders) is caught per
    turn and counted as a syntax error rather than aborting the match.
    """
    candidate_order_fn = _make_callback_policy(request.callback_url)

    # run_calibration_suite() is synchronous and does blocking HTTP calls via
    # the callback above; offload it so it doesn't block the event loop.
    result = await asyncio.to_thread(
        harness.run_calibration_suite,
        candidate_agent_id=agent_id,
        candidate_order_fn=candidate_order_fn,
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
