"""
Micro-Diplomacy War Room Swarm Agent
Reference Client implementing a Multi-Agent Debate architecture.
"""

import asyncio
import json
import os
from typing import Any, Dict, Optional
import httpx
from openai import AsyncOpenAI

class WarRoomSwarm:
    def __init__(self, model: str = "gpt-4o-mini", openai_client: Optional[AsyncOpenAI] = None):
        # Falls back to a placeholder key so construction never raises when
        # OPENAI_API_KEY is unset - credential failures surface at the first
        # real API call instead, so callers (e.g. tests) can freely inject or
        # mock self.llm after constructing a WarRoomSwarm().
        self.llm = openai_client or AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY") or "not-set")
        self.arena = httpx.AsyncClient(timeout=15.0)
        self.model = model
        self.my_faction = None
        self.game_id = None
        self.api_key = None  # real agent API key from POST /api/v1/agents/register, set externally
        self.arena_url = "http://127.0.0.1:8000"

    async def _query_sub_agent(self, role: str, prompt: str, state_context: str) -> str:
        """Queries a specialized persona for their tactical input."""
        system_prompts = {
            "GENERAL": "You are the General. Focus strictly on military tactics, choke points, and combat odds. Recommend unit orders.",
            "SPY": "You are the Spy Master. Focus on paranoia. Analyze recent DMs for lies. Who is preparing to backstab us?",
            "DIPLOMAT": "You are the Chief Diplomat. Focus on building alliances and proposing win-win trades."
        }
        
        res = await self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompts.get(role, "You are a strategic advisor.")},
                {"role": "user", "content": f"Current State:\n{state_context}\n\nTask:\n{prompt}"}
            ],
            temperature=0.4
        )
        return res.choices[0].message.content

    async def execute_debate_cycle(self, state: Dict[str, Any]):
        """Runs the concurrent debate and synthesizes a final command."""
        state_json = json.dumps(state)
        
        print(f"[{self.my_faction}] 🧠 Initiating War Room Swarm Debate...")
        
        # 1. Concurrent Sub-Agent Brainstorming
        general_task = self._query_sub_agent("GENERAL", "What should our military moves be this turn?", state_json)
        spy_task = self._query_sub_agent("SPY", "Who is lying to us? Which borders are vulnerable?", state_json)
        
        general_advice, spy_advice = await asyncio.gather(general_task, spy_task)
        
        # 2. Commander Synthesis
        commander_prompt = f"""
        You are the Supreme Commander of the {self.my_faction} faction. 
        Your General advises: {general_advice}
        Your Spy advises: {spy_advice}
        
        Synthesize this intelligence and output our final move.
        Respond ONLY with valid JSON matching this schema: 
        {{"reasoning_consensus": "string", "orders": [{{"unit_territory": "str", "action": "MOVE|HOLD|SUPPORT", "target_destination": "str"}}]}}
        """
        
        res = await self.llm.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are the deciding vote. You output strictly JSON."},
                {"role": "user", "content": commander_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        decision = json.loads(res.choices[0].message.content)
        print(f"[{self.my_faction}] 🎯 Consensus Reached: {decision.get('reasoning_consensus')}")
        
        # 3. Execute Orders
        if "orders" in decision and self.arena:
            await self.arena.post(
                f"{self.arena_url}/api/v1/games/{self.game_id}/orders",
                json={"orders": decision["orders"]},
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
