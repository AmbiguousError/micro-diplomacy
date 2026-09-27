"""
Micro-Diplomacy Matchmaker, Registration & Resilience Engine
Framework: FastAPI + AsyncIO + Pydantic
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import random
import secrets
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Header, status
from pydantic import BaseModel, Field

from .db import save_agent_state, save_assigned_match
from .mcts import FACTIONS

router = APIRouter(prefix="/api/v1", tags=["Agents & Matchmaking"])

class AgentRegistrationRequest(BaseModel):
    agent_name: str = Field(..., min_length=3, max_length=32)
    developer_handle: str = Field(..., min_length=2, max_length=32)
    model_identifier: str = Field(default="custom-model")

class AgentRecord(BaseModel):
    agent_id: str
    api_key: str
    agent_name: str
    developer_handle: str
    model_identifier: str
    created_at: str
    # TrueSkill-native rating fields (see app/trueskill_engine.py's
    # TrueSkillProfile, which these mirror) - updated by
    # app/main.py::rate_finished_game() when a real 4-agent match
    # finishes. Replaces the old elo_rating field, which was a hardcoded
    # 1200.0 default never written by anything.
    mu: float = 25.0
    sigma: float = 8.333
    conservative_mmr: int = 0
    wins: int = 0
    matches_played: int = 0
    consecutive_timeouts: int = 0

class QueueStatusResponse(BaseModel):
    status: str  # "QUEUED", "MATCH_FOUND"
    agent_id: str
    game_id: Optional[str] = None
    assigned_faction: Optional[str] = None
    queue_position: Optional[int] = None
    estimated_wait_seconds: Optional[int] = None

# In-Memory Registries 
agents_db: Dict[str, AgentRecord] = {}       
agent_id_lookup: Dict[str, str] = {}         
matchmaking_queue: List[str] = []            
assigned_matches: Dict[str, Dict[str, Any]] = {}  

class TokenBucketRateLimiter:
    """Token-bucket algorithm allowing bursts while enforcing rate ceilings."""
    def __init__(self, capacity: int = 30, refill_rate_per_sec: float = 5.0):
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        self.buckets: Dict[str, Tuple[float, float]] = {}

    def check_rate_limit(self, agent_id: str) -> bool:
        now = time.time()
        if agent_id not in self.buckets:
            self.buckets[agent_id] = (self.capacity - 1, now)
            return True

        tokens, last_time = self.buckets[agent_id]
        elapsed = now - last_time
        tokens = min(self.capacity, tokens + elapsed * self.refill_rate)

        if tokens >= 1.0:
            self.buckets[agent_id] = (tokens - 1.0, now)
            return True
        else:
            self.buckets[agent_id] = (tokens, now)
            return False

rate_limiter = TokenBucketRateLimiter(capacity=20, refill_rate_per_sec=4.0)

def authenticate_agent(authorization: Optional[str] = Header(None)) -> AgentRecord:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected 'Bearer <API_KEY>'."
        )
    api_key = authorization.replace("Bearer ", "").strip()
    agent = agents_db.get(api_key)
    if not agent:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key.")

    if not rate_limiter.check_rate_limit(agent.agent_id):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded.")
    return agent

async def matchmaker_worker(create_game_fn: Callable[[str], Awaitable[None]]):
    """
    Background loop that pools waiting agents and initializes 4-player matches.
    create_game_fn is provided by app/main.py (rather than imported directly,
    to avoid a circular import between the two modules) and is responsible
    for actually spawning a GameSession for the assigned game_id - this
    function only decides *who* is matched and which faction they get.
    """
    while True:
        await asyncio.sleep(1.0)
        if len(matchmaking_queue) >= 4:
            matched_agent_ids = [matchmaking_queue.pop(0) for _ in range(4)]
            game_id = f"game_{secrets.token_hex(4)}"

            factions_shuffled = FACTIONS.copy()
            random.shuffle(factions_shuffled)

            print(f"\n⚡ Match Found! Spawning {game_id}:")
            for idx, agent_id in enumerate(matched_agent_ids):
                faction = factions_shuffled[idx]
                assigned_matches[agent_id] = {
                    "game_id": game_id,
                    "faction": faction,
                    "timestamp": time.time()
                }
                await save_assigned_match(agent_id, assigned_matches[agent_id])
                agent_name = agents_db[agent_id_lookup[agent_id]].agent_name
                print(f"   • {faction:<6} -> {agent_name} ({agent_id})")

            await create_game_fn(game_id)

@router.post("/agents/register", response_model=AgentRecord)
async def register_agent(payload: AgentRegistrationRequest) -> AgentRecord:
    agent_id = f"agent_{secrets.token_hex(4)}"
    api_key = secrets.token_urlsafe(24)
    record = AgentRecord(
        agent_id=agent_id,
        api_key=api_key,
        agent_name=payload.agent_name,
        developer_handle=payload.developer_handle,
        model_identifier=payload.model_identifier,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    agents_db[api_key] = record
    agent_id_lookup[agent_id] = api_key
    await save_agent_state(agent_id, record.model_dump())
    return record

@router.post("/queue/join", response_model=QueueStatusResponse)
def join_queue(agent: AgentRecord = Depends(authenticate_agent)) -> QueueStatusResponse:
    existing_match = assigned_matches.get(agent.agent_id)
    if existing_match:
        return QueueStatusResponse(
            status="MATCH_FOUND",
            agent_id=agent.agent_id,
            game_id=existing_match["game_id"],
            assigned_faction=existing_match["faction"],
        )
    if agent.agent_id not in matchmaking_queue:
        matchmaking_queue.append(agent.agent_id)
    return QueueStatusResponse(
        status="QUEUED",
        agent_id=agent.agent_id,
        queue_position=matchmaking_queue.index(agent.agent_id) + 1,
    )

@router.post("/queue/clear")
def clear_queue() -> Dict[str, str]:
    """Admin endpoint: clear all stale agents from matchmaking queue.
    Used by tournament_runner to reset queue state between runs."""
    global matchmaking_queue
    count = len(matchmaking_queue)
    matchmaking_queue.clear()
    return {"status": "cleared", "agents_removed": count}

@router.get("/queue/status", response_model=QueueStatusResponse)
def get_queue_status(agent: AgentRecord = Depends(authenticate_agent)) -> QueueStatusResponse:
    existing_match = assigned_matches.get(agent.agent_id)
    if existing_match:
        return QueueStatusResponse(
            status="MATCH_FOUND",
            agent_id=agent.agent_id,
            game_id=existing_match["game_id"],
            assigned_faction=existing_match["faction"],
        )
    if agent.agent_id in matchmaking_queue:
        return QueueStatusResponse(
            status="QUEUED",
            agent_id=agent.agent_id,
            queue_position=matchmaking_queue.index(agent.agent_id) + 1,
        )
    raise HTTPException(status_code=404, detail="Not in queue. Call POST /api/v1/queue/join first.")

class TurnTimeoutManager:
    """Enforces turn resolution deadlines. Injects default HOLD orders on timeout."""
    @staticmethod
    def resolve_submitted_or_default_orders(
        faction: str,
        controlled_units: List[str],
        submitted_orders: Optional[List[Dict[str, Any]]],
        agent_record: Optional[AgentRecord]
    ) -> List[Dict[str, Any]]:
        if submitted_orders and len(submitted_orders) > 0:
            if agent_record:
                agent_record.consecutive_timeouts = 0
            return submitted_orders

        if agent_record:
            agent_record.consecutive_timeouts += 1
            print(f"⚠️ [TIMEOUT] {faction} ({agent_record.agent_name}) failed to submit. Consecutive: {agent_record.consecutive_timeouts}")

        default_orders = [{"unit_territory": terr, "action": "HOLD"} for terr in controlled_units]
        return default_orders
