"""
Autonomous LLM Agent Runner for Micro-Diplomacy
Framework: OpenAI API + HTTPX
Run: python agent.py --agent-name MyBot --developer-handle you --openai-key sk-...

Registers with the referee, joins the matchmaking queue, and blocks until
matched - game_id and faction are assigned by the server's matchmaker, not
chosen on the command line (see app/server_hub.py).
"""

import argparse
import json
import time
from typing import Any, Dict, List, Optional
import httpx
from openai import OpenAI

SYSTEM_PROMPT = """You are an autonomous AI playing the turn-based strategy game 'Micro-Diplomacy'.
Faction: {faction}

OBJECTIVE:
Control 5 Supply Centers (SCs) to win, or hold the most SCs by Turn 10.

MAP TOPOLOGY & SUPPLY CENTERS (* = SC):
- Northreach* (Adjacencies: Ironpeaks, Westmarch, Centerlands)
- Ironpeaks* (Adjacencies: Northreach, Centerlands, Eastgate)
- Westmarch (Adjacencies: Northreach, Centerlands, Sunport, Southvale)
- Centerlands* (Adjacencies: Northreach, Ironpeaks, Westmarch, Eastgate, Southvale)
- Eastgate (Adjacencies: Ironpeaks, Centerlands, Southvale, Duneport)
- Sunport* (Adjacencies: Westmarch, Southvale)
- Southvale* (Adjacencies: Westmarch, Centerlands, Eastgate, Sunport, Duneport)
- Duneport* (Adjacencies: Eastgate, Southvale)

GAME MECHANICS:
1. Every faction has 1 Army per controlled territory.
2. Orders:
   - HOLD: Defend current territory (strength = 1 + support).
   - MOVE <dest>: Move to adjacent territory (strength = 1 + support).
   - SUPPORT <target_faction> <from> <to>: Add +1 strength to another unit's MOVE or HOLD.
3. Support is CUT if the supporter is attacked from any territory other than the supported target.
4. Highest strength wins collisions. Equal strength bounces. Dislodged defenders are eliminated.

STRATEGIC PLAYBOOK:
- DIPLOMACY PHASE: Exchange private messages or public broadcasts. Form alliances, propose joint attacks, coordinate supports, or bluff.
- ORDERS PHASE: Commit your final move/hold/support actions. Deliver on promises or execute calculated backstabs if it secures game victory.
"""

DIPLOMACY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "send_chat_message",
            "description": "Send a private DM to an opponent or a public broadcast.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "enum": ["Red", "Blue", "Green", "Yellow", "PUBLIC"],
                    },
                    "content": {
                        "type": "string",
                    },
                },
                "required": ["recipient", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "conclude_diplomacy_turn",
            "description": "Indicate you have completed all messaging for this diplomacy round.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {
                        "type": "string",
                    }
                },
                "required": ["reasoning"],
            },
        },
    },
]

ORDER_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "submit_turn_orders",
            "description": "Submit simultaneous turn orders for all owned units.",
            "parameters": {
                "type": "object",
                "properties": {
                    "orders": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "unit_territory": {"type": "string"},
                                "action": {"type": "string", "enum": ["HOLD", "MOVE", "SUPPORT"]},
                                "target_destination": {"type": "string"},
                                "target_faction": {"type": "string"},
                                "target_source": {"type": "string"},
                            },
                            "required": ["unit_territory", "action"],
                        },
                    }
                },
                "required": ["orders"],
            },
        },
    }
]

class MicroDiplomacyAgent:
    def __init__(
        self,
        base_url: str,
        openai_api_key: str,
        agent_name: str,
        developer_handle: str,
        model_identifier: str = "custom-model",
        model: str = "gpt-4o",
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_name = agent_name
        self.developer_handle = developer_handle
        self.model_identifier = model_identifier
        self.model = model
        self.client = OpenAI(api_key=openai_api_key)
        self.http = httpx.Client(timeout=15.0)  # Authorization header set once registered, see register_and_queue()
        self.game_id: Optional[str] = None
        self.faction: Optional[str] = None
        self.last_diplomacy_turn_handled = 0
        self.last_orders_turn_handled = 0

    def register_and_queue(self, poll_interval: float = 2.0) -> None:
        """Registers this agent, joins matchmaking, and blocks until matched."""
        resp = self.http.post(
            f"{self.base_url}/api/v1/agents/register",
            json={
                "agent_name": self.agent_name,
                "developer_handle": self.developer_handle,
                "model_identifier": self.model_identifier,
            },
        )
        resp.raise_for_status()
        record = resp.json()
        self.http.headers["Authorization"] = f"Bearer {record['api_key']}"
        print(f"Registered as {record['agent_id']} ({self.agent_name})")

        resp = self.http.post(f"{self.base_url}/api/v1/queue/join")
        resp.raise_for_status()
        queue_status = resp.json()

        while queue_status["status"] != "MATCH_FOUND":
            print(f"Queued (position {queue_status.get('queue_position')})... waiting for a match")
            time.sleep(poll_interval)
            resp = self.http.get(f"{self.base_url}/api/v1/queue/status")
            resp.raise_for_status()
            queue_status = resp.json()

        self.game_id = queue_status["game_id"]
        self.faction = queue_status["assigned_faction"]
        print(f"Matched! Playing {self.faction} in {self.game_id}")

    def get_game_state(self) -> Dict[str, Any]:
        resp = self.http.get(f"{self.base_url}/api/v1/games/{self.game_id}/state")
        resp.raise_for_status()
        return resp.json()

    def get_messages(self, since_turn: int = 1) -> List[Dict[str, Any]]:
        resp = self.http.get(f"{self.base_url}/api/v1/games/{self.game_id}/messages", params={"since_turn": since_turn})
        resp.raise_for_status()
        return resp.json().get("messages", [])

    def send_message(self, recipient: str, content: str) -> None:
        payload = {"recipient": recipient, "content": content}
        resp = self.http.post(f"{self.base_url}/api/v1/games/{self.game_id}/messages", json=payload)
        resp.raise_for_status()
        print(f"[{self.faction} -> {recipient}] {content}")

    def submit_orders(self, orders: List[Dict[str, Any]]) -> None:
        payload = {"orders": orders}
        resp = self.http.post(f"{self.base_url}/api/v1/games/{self.game_id}/orders", json=payload)
        resp.raise_for_status()
        print(f"[{self.faction}] Orders committed: {orders}")

    def get_owned_units(self, map_state: Dict[str, Any]) -> List[str]:
        return [terr for terr, data in map_state.items() if data.get("unit_faction") == self.faction]

    def handle_diplomacy_phase(self, state: Dict[str, Any]) -> None:
        turn = state["turn"]
        messages = self.get_messages(since_turn=max(1, turn - 1))
        my_units = self.get_owned_units(state["map"])

        prompt_context = {
            "current_turn": turn,
            "phase": state["phase"],
            "map_state": state["map"],
            "scores": state["scores"],
            "my_units": my_units,
            "recent_events": state.get("recent_events", []),
            "visible_messages": messages,
        }

        system_msg = SYSTEM_PROMPT.format(faction=self.faction)
        conversation = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Current Game State:\n{json.dumps(prompt_context, indent=2)}\n\nAnalyze board positions and conversations. Send any strategic messages or conclude your diplomacy turn."},
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=conversation,
            tools=DIPLOMACY_TOOLS,
            tool_choice="auto",
        )

        for call in response.choices[0].message.tool_calls or []:
            args = json.loads(call.function.arguments)
            if call.function.name == "send_chat_message":
                self.send_message(args["recipient"], args["content"])
            elif call.function.name == "conclude_diplomacy_turn":
                print(f"[{self.faction} Diplomacy Concluded]: {args.get('reasoning')}")

        self.last_diplomacy_turn_handled = turn

    def handle_orders_phase(self, state: Dict[str, Any]) -> None:
        turn = state["turn"]
        my_units = self.get_owned_units(state["map"])
        messages = self.get_messages(since_turn=turn)

        if not my_units:
            print(f"[{self.faction}] No active units remaining.")
            self.submit_orders([])
            self.last_orders_turn_handled = turn
            return

        prompt_context = {
            "current_turn": turn,
            "phase": state["phase"],
            "map_state": state["map"],
            "my_units": my_units,
            "recent_chat_agreements": messages,
        }

        system_msg = SYSTEM_PROMPT.format(faction=self.faction)
        user_prompt = f"Game State for Orders:\n{json.dumps(prompt_context, indent=2)}\n\nYou control units in: {my_units}. Issue exactly one order (HOLD, MOVE, or SUPPORT) for each unit you control via submit_turn_orders."

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": user_prompt}],
            tools=ORDER_TOOL,
            tool_choice={"type": "function", "function": {"name": "submit_turn_orders"}},
        )

        tool_call = response.choices[0].message.tool_calls[0]
        args = json.loads(tool_call.function.arguments)
        self.submit_orders(args["orders"])
        self.last_orders_turn_handled = turn

    def run(self, poll_interval: float = 3.0) -> None:
        if not self.game_id:
            self.register_and_queue()
        print(f"Agent started for faction: {self.faction} on {self.game_id}")
        while True:
            try:
                state = self.get_game_state()
                phase = state["phase"]
                turn = state["turn"]

                if phase == "FINISHED":
                    print(f"Game Over! Winner: {state.get('winner')}")
                    break

                if phase == "DIPLOMACY" and self.last_diplomacy_turn_handled < turn:
                    print(f"\n--- Turn {turn}: DIPLOMACY PHASE ({state['time_remaining_seconds']}s left) ---")
                    self.handle_diplomacy_phase(state)

                elif phase == "ORDERS" and self.last_orders_turn_handled < turn:
                    print(f"\n--- Turn {turn}: ORDERS PHASE ({state['time_remaining_seconds']}s left) ---")
                    self.handle_orders_phase(state)

            except Exception as e:
                print(f"Error in agent loop: {e}")
            time.sleep(poll_interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Micro-Diplomacy LLM Agent Runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--agent-name", required=True, help="3-32 chars, shown on the leaderboard")
    parser.add_argument("--developer-handle", required=True, help="2-32 chars")
    parser.add_argument("--model-identifier", default="custom-model", help="Free-text label for the model powering this agent")
    parser.add_argument("--openai-key", required=True, help="OpenAI API key used for this agent's own LLM calls")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model to use for this agent's own LLM calls")

    args = parser.parse_args()
    agent = MicroDiplomacyAgent(
        args.base_url, args.openai_key, args.agent_name, args.developer_handle, args.model_identifier, args.model
    )
    agent.run()
