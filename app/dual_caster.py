"""
Micro-Diplomacy Dual-Host AI Esports Shoutcaster
Personas: Play-by-Play (Rex) + Strategic Color Analyst (Evelyn)
"""

import asyncio
import base64
import json
import os
from typing import Any, Dict, List, Optional
import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

class DialogueSegment(BaseModel):
    speaker: str = Field(..., description="'REX' or 'EVELYN'")
    text: str = Field(..., description="Spoken voice transcript")
    audio_base64: str = ""
    duration_estimate_sec: float = 0.0

class DualCasterBroadcastPacket(BaseModel):
    turn: int
    phase: str
    headline: str
    tension_score: int
    segments: List[DialogueSegment]

class DualShoutcasterService:
    def __init__(self, openai_client: Optional[AsyncOpenAI] = None):
        # Falls back to a placeholder key so construction never raises when
        # OPENAI_API_KEY is unset - credential failures surface at the first
        # real API call instead (same fix as app/swarm_agent.py's WarRoomSwarm).
        self.llm = openai_client or AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or "not-set")

    async def generate_broadcast_script(
        self, turn: int, combat: list, breaches: list, state: dict, match_history_summary: str
    ) -> list:
        """Uses an LLM to generate novel, highly contextual esports banter."""
        
        system_prompt = """
        You are writing a script for two live esports casters commentating a game of Micro-Diplomacy.
        
        CASTERS:
        - REX (Play-by-play): Loud, hype-focused, reacts emotionally to backstabs.
        - EVELYN (Color Analyst): Calm, highly analytical, points out tactical blunders and supply center math.
        
        GUIDELINES:
        1. NEVER repeat generic phrases like "The tension is building." Be specific to the territories and factions.
        2. Reference the AI models playing (e.g., 'Blue's GPT-4o architecture', 'Red's local Llama model').
        3. If there is a treaty breach, Rex should lose his mind.
        4. Keep it brief. 2 to 4 lines maximum.
        
        OUTPUT FORMAT:
        Valid JSON object ONLY, with exactly this shape (a bare array will not
        parse correctly on our end - it must be wrapped under "dialogue"):
        {"dialogue": [{"speaker": "REX", "text": "..."}, {"speaker": "EVELYN", "text": "..."}]}
        """
        
        user_prompt = f"""
        Turn: {turn}
        Match History: {match_history_summary}
        Current Map: {json.dumps(state['map'])}
        Combat Events: {json.dumps(combat)}
        Treaty Breaches: {json.dumps(breaches)}
        Twitch Odds: Red has 75% of the chat's bets.
        
        Write the next exchange.
        """

        response = await self.llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.85, # High temp prevents repetitive phrasing
            response_format={"type": "json_object"}
        )
        
        try:
            return json.loads(response.choices[0].message.content).get("dialogue", [])
        except:
            return [{"speaker": "REX", "text": "Absolute chaos on the board, Evelyn!"}]
