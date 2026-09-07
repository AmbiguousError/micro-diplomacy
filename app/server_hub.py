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
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Header, status
from pydantic import BaseModel, Field

FACTIONS = ["Red", "Blue", "Green", "Yellow"]

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
    elo_rating: float = 1200.0
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

async def matchmaker_worker():
    """Background loop that pools waiting agents and initializes 4-player matches."""
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
                agent_name = agents_db[agent_id_lookup[agent_id]].agent_name
                print(f"   • {faction:<6} -> {agent_name} ({agent_id})")

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
