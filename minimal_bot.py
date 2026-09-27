#!/usr/bin/env python3
"""
Minimal Micro-Diplomacy Bot Template
Use this as a starting point for custom LLM integrations.
"""

import httpx
import time
import json
from typing import Dict, Any, Optional, List

class MinimalBot:
    def __init__(self, base_url: str, agent_name: str, developer_handle: str):
        self.base_url = base_url.rstrip("/")
        self.agent_name = agent_name
        self.developer_handle = developer_handle
        self.http = httpx.Client(timeout=15.0)
        self.game_id: Optional[str] = None
        self.faction: Optional[str] = None
        self.api_key: Optional[str] = None

    def register(self) -> None:
        """Step 1: Register with the server."""
        print("[REGISTER] Registering bot...")
        resp = self.http.post(
            f"{self.base_url}/api/v1/agents/register",
            json={
                "agent_name": self.agent_name,
                "developer_handle": self.developer_handle,
                "model_identifier": "minimal-bot-v1",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self.api_key = data["api_key"]
        self.http.headers["Authorization"] = f"Bearer {self.api_key}"
        print(f"[REGISTER] ✓ Registered as {data['agent_id']}")

    def join_queue(self) -> None:
        """Step 2: Join matchmaking queue."""
        print("[QUEUE] Joining matchmaking queue...")
        resp = self.http.post(f"{self.base_url}/api/v1/queue/join")
        resp.raise_for_status()

        while True:
            resp = self.http.get(f"{self.base_url}/api/v1/queue/status")
            resp.raise_for_status()
            status = resp.json()

            if status["status"] == "MATCH_FOUND":
                self.game_id = status["game_id"]
                self.faction = status["assigned_faction"]
                print(f"[QUEUE] ✓ Matched! Playing {self.faction} in {self.game_id}")
                break

            pos = status.get("queue_position", "?")
            print(f"[QUEUE] Position {pos}... waiting")
            time.sleep(2.0)

    def get_game_state(self) -> Dict[str, Any]:
        """Fetch current game state."""
        resp = self.http.get(f"{self.base_url}/api/v1/games/{self.game_id}/state")
        resp.raise_for_status()
        return resp.json()

    def get_my_units(self, state: Dict[str, Any]) -> List[str]:
        """Extract territories where I have units."""
        return [t for t, data in state["map"].items() if data.get("unit_faction") == self.faction]

    def get_messages(self, since_turn: int = 1) -> List[Dict[str, Any]]:
        """Fetch chat messages since a given turn."""
        resp = self.http.get(
            f"{self.base_url}/api/v1/games/{self.game_id}/messages",
            params={"since_turn": since_turn}
        )
        resp.raise_for_status()
        return resp.json().get("messages", [])

    def send_message(self, recipient: str, content: str) -> None:
        """Send a private or public message."""
        resp = self.http.post(
            f"{self.base_url}/api/v1/games/{self.game_id}/messages",
            json={"recipient": recipient, "content": content}
        )
        resp.raise_for_status()
        print(f"[{self.faction} -> {recipient}] {content}")

    def submit_orders(self, orders: List[Dict[str, Any]]) -> None:
        """Submit turn orders."""
        resp = self.http.post(
            f"{self.base_url}/api/v1/games/{self.game_id}/orders",
            json={"orders": orders}
        )
        resp.raise_for_status()
        print(f"[{self.faction}] Orders: {orders}")

    def make_decision(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Override this with your LLM logic."""
        # This is where you'd call your LLM (Claude, Ollama, etc.)
        # For now, just HOLD all units
        my_units = self.get_my_units(state)
        return [{"unit_territory": unit, "action": "HOLD"} for unit in my_units]

    def run(self) -> None:
        """Main bot loop."""
        self.register()
        self.join_queue()

        print(f"[START] Game begun for {self.faction}")
        last_diplomacy_turn = 0
        last_orders_turn = 0

        while True:
            try:
                state = self.get_game_state()

                if state["phase"] == "FINISHED":
                    print(f"[END] Game over! Winner: {state.get('winner')}")
                    break

                # DIPLOMACY phase: send messages
                if state["phase"] == "DIPLOMACY" and state["turn"] > last_diplomacy_turn:
                    print(f"\n=== Turn {state['turn']}: DIPLOMACY ({state['time_remaining_seconds']}s) ===")
                    self.send_message("PUBLIC", f"Turn {state['turn']}: I'm ready to play!")
                    last_diplomacy_turn = state["turn"]

                # ORDERS phase: submit orders
                if state["phase"] == "ORDERS" and state["turn"] > last_orders_turn:
                    print(f"\n=== Turn {state['turn']}: ORDERS ({state['time_remaining_seconds']}s) ===")
                    orders = self.make_decision(state)
                    if orders:
                        self.submit_orders(orders)
                    last_orders_turn = state["turn"]

            except Exception as e:
                print(f"[ERROR] {e}")

            time.sleep(2.0)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-name", default="MinimalBot", help="Bot display name")
    parser.add_argument("--developer-handle", default="developer", help="Your handle")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Server URL")
    args = parser.parse_args()

    bot = MinimalBot(
        base_url=args.base_url,
        agent_name=args.agent_name,
        developer_handle=args.developer_handle,
    )
    bot.run()
