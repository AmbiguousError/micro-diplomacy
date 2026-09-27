#!/usr/bin/env python3
"""
Micro-Diplomacy Bot using Local Ollama
Calls a local Ollama model each turn to decide orders (HOLD/MOVE) and,
during the DIPLOMACY phase, an optional public message.
"""

import argparse
import hashlib
import json
import string
import time
import httpx
import yaml
from typing import Any, Dict, List, Optional

# Built-in fallback if --prompts-file is missing or doesn't contain the
# requested variant, so the bot still runs without prompts.yaml present.
DEFAULT_PROMPTS = {
    "orders": """You are playing faction $faction in a Diplomacy-style strategy game on an 8-territory map.
Your goal is to maximize the number of supply centers you control. You win by controlling 5, or having the most at turn 10.
Staying in place (HOLD) never gains you a new supply center - only MOVEing onto an empty or enemy-held supply center can capture it.
Prefer MOVEing onto an EMPTY supply center whenever one of your units is adjacent to one. Only HOLD if every adjacent territory is unfavorable.
You may also spend a unit's turn on SPY instead of HOLD/MOVE: it still defends its own territory, but reveals that faction's real MOVE orders and private DMs for this turn only.

Your units and their real options this turn:
$unit_briefs

Rival factions you could SPY on: $enemy_factions

Respond with ONLY a JSON object in exactly this shape, no other text:
{"orders": [{"unit_territory": "<territory>", "action": "HOLD"}, {"unit_territory": "<territory>", "action": "MOVE", "target_destination": "<adjacent territory>"}, {"unit_territory": "<territory>", "action": "SPY", "target_faction": "<rival faction>"}]}

Include exactly one order for each of your units: $my_units
""",
    "message": """You are playing faction $faction in a Diplomacy-style game, turn $turn, diplomacy phase.

Current map ownership: $map
Scores (supply centers held): $scores

You may optionally send one short public message to the other players (a threat, alliance offer, or taunt), under 20 words.

You can also propose a formal treaty with another faction (NON_AGGRESSION, DMZ, or SUPPORT_PROMISE over specific territories), and/or sign a pending treaty someone has proposed to you:
Treaties awaiting your signature: $pending_treaties

Respond with ONLY a JSON object, no other text:
{"send": true, "content": "<your message>", "propose_treaty": {"signatory": "<rival faction>", "treaty_type": "NON_AGGRESSION", "target_territories": ["<territory>"], "duration_turns": 5}, "sign_treaty_id": "<treaty_id>"}
Omit "propose_treaty" and/or "sign_treaty_id" entirely if you have none to offer or sign this turn. Use {"send": false} for the message portion if you have nothing to say.
""",
}


class OllamaBot:
    def __init__(
        self,
        base_url: str,
        agent_name: str,
        developer_handle: str,
        ollama_model: str = "mistral",
        ollama_url: str = "http://localhost:11434",
        prompts_file: Optional[str] = "prompts.yaml",
        prompt_name: str = "default",
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_name = agent_name
        self.developer_handle = developer_handle
        self.ollama_model = ollama_model
        self.ollama_url = ollama_url.rstrip("/")
        self.prompt_name = prompt_name
        self.prompts = self._load_prompts(prompts_file, prompt_name)

        self.http = httpx.Client(timeout=120.0)
        self.ollama_http = httpx.Client(timeout=60.0)
        self.game_id: Optional[str] = None
        self.faction: Optional[str] = None
        self.last_orders_turn = 0
        self.last_diplomacy_turn = 0
        self.previous_map_state: Optional[Dict] = None  # Track previous turn's map state
        self.vacated_scs: List[str] = []  # Supply centers vacated last turn

    def _load_prompts(self, prompts_file: Optional[str], prompt_name: str) -> Dict[str, str]:
        prompts = dict(DEFAULT_PROMPTS)
        if not prompts_file:
            return prompts
        try:
            with open(prompts_file) as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            print(f"[PROMPTS] {prompts_file} not found, using built-in defaults")
            return prompts

        variant = data.get(prompt_name)
        if not variant:
            print(f"[PROMPTS] '{prompt_name}' not found in {prompts_file}, using built-in defaults")
            return prompts

        prompts.update(variant)
        print(f"[PROMPTS] Loaded '{prompt_name}' from {prompts_file}")
        return prompts

    def register_agent(self) -> None:
        print("[REGISTER] Registering bot...")
        resp = self.http.post(
            f"{self.base_url}/api/v1/agents/register",
            json={
                "agent_name": self.agent_name,
                "developer_handle": self.developer_handle,
                "model_identifier": f"ollama-{self.ollama_model}",
            },
        )
        resp.raise_for_status()
        record = resp.json()
        self.agent_id = record['agent_id']
        self.http.headers["Authorization"] = f"Bearer {record['api_key']}"
        print(f"[REGISTER] ✓ Registered as {record['agent_id']}")

    def join_queue(self) -> None:
        print("[QUEUE] Joining matchmaking queue...")
        resp = self.http.post(f"{self.base_url}/api/v1/queue/join")
        resp.raise_for_status()

        while True:
            resp = self.http.get(f"{self.base_url}/api/v1/queue/status")
            resp.raise_for_status()
            queue_status = resp.json()

            if queue_status["status"] == "MATCH_FOUND":
                self.game_id = queue_status["game_id"]
                self.faction = queue_status["assigned_faction"]
                print(f"[QUEUE] ✓ Matched! Playing {self.faction} in {self.game_id}")
                break

            pos = queue_status.get("queue_position", "?")
            print(f"[QUEUE] Position {pos}... waiting")
            time.sleep(2.0)

    def get_game_state(self) -> Dict[str, Any]:
        resp = self.http.get(f"{self.base_url}/api/v1/games/{self.game_id}/state")
        resp.raise_for_status()
        return resp.json()

    def get_owned_units(self, map_state: Dict[str, Any]) -> List[str]:
        return [terr for terr, data in map_state.items() if data.get("unit_faction") == self.faction]

    def detect_vacated_scs(self, current_map: Dict[str, Any]) -> List[str]:
        """Detect supply centers that were occupied last turn but are now empty."""
        if not self.previous_map_state:
            self.previous_map_state = current_map
            return []

        vacated = []
        supply_centers = {"Northreach", "Ironpeaks", "Centerlands", "Sunport", "Southvale", "Duneport"}

        for sc in supply_centers:
            prev = self.previous_map_state.get(sc, {})
            curr = current_map.get(sc, {})

            # SC was occupied last turn but is now unowned
            if prev.get("unit_faction") and not curr.get("unit_faction"):
                vacated.append(sc)

        self.previous_map_state = current_map
        self.vacated_scs = vacated
        return vacated

    def submit_orders(self, orders: List[Dict[str, Any]]) -> None:
        # Verify prompt before submitting orders (season compliance)
        # In ladder mode (no active season), this just logs and allows
        if not self.verify_prompt():
            # Only fail if verification explicitly rejected (e.g., hash mismatch)
            # Ladder mode verification always returns True
            print(f"[{self.faction}] Prompt verification failed, skipping orders")
            return

        payload = {
            "orders": orders,
            "_compliance": {
                "prompt_hash": self.compute_prompt_hash(),
                "agent_id": self.agent_id,
            }
        }

        resp = self.http.post(
            f"{self.base_url}/api/v1/games/{self.game_id}/orders",
            json=payload
        )
        resp.raise_for_status()
        order_strs = []
        for o in orders:
            unit = o.get("unit_territory", "?")
            action = o.get("action", "?")
            target = o.get("target_destination") or o.get("target_faction")
            if target:
                order_strs.append(f"{unit} {action} -> {target}")
            else:
                order_strs.append(f"{unit} {action}")
        print(f"[{self.faction}] Orders ({len(orders)}): {'; '.join(order_strs)}")

    def send_message(self, recipient: str, content: str) -> None:
        resp = self.http.post(
            f"{self.base_url}/api/v1/games/{self.game_id}/messages",
            json={"recipient": recipient, "content": content},
        )
        resp.raise_for_status()
        display = content[:80] + "..." if len(content) > 80 else content
        print(f"[{self.faction}] Message to {recipient}: {display}")

    def get_pending_treaties(self) -> List[Dict[str, Any]]:
        resp = self.http.get(f"{self.base_url}/api/v1/games/{self.game_id}/treaties")
        resp.raise_for_status()
        treaties = resp.json().get("treaties", [])
        return [t for t in treaties if t["signatory"] == self.faction and t["status"] == "PENDING"]

    def propose_treaty(self, signatory: str, treaty_type: str, target_territories: List[str], duration_turns: int) -> None:
        resp = self.http.post(
            f"{self.base_url}/api/v1/games/{self.game_id}/treaties",
            json={
                "signatory": signatory,
                "treaty_type": treaty_type,
                "target_territories": target_territories,
                "duration_turns": duration_turns,
            },
        )
        if resp.status_code >= 400:
            print(f"[{self.faction}] Treaty proposal rejected ({resp.status_code}): {resp.text}")
            return
        treaty = resp.json()
        print(f"[{self.faction}] Proposed {treaty_type} treaty {treaty['treaty_id']} to {signatory} over {target_territories}")

    def sign_treaty(self, treaty_id: str) -> None:
        resp = self.http.post(f"{self.base_url}/api/v1/games/{self.game_id}/treaties/{treaty_id}/sign")
        if resp.status_code >= 400:
            print(f"[{self.faction}] Treaty sign rejected ({resp.status_code}): {resp.text}")
            return
        print(f"[{self.faction}] Signed treaty {treaty_id}")

    def compute_prompt_hash(self) -> str:
        """Compute SHA256 hash of current prompts (all variants concatenated)."""
        prompt_text = ""
        for name, variant in self.prompts.items():
            if isinstance(variant, dict):
                prompt_text += f"{name}:" + str(variant) + "\n"
            else:
                prompt_text += variant + "\n"
        return hashlib.sha256(prompt_text.encode()).hexdigest()

    def register_prompt_for_season(self, season_id: str) -> bool:
        """Register this agent's prompt hash for a tournament season.

        Returns False on error, but the bot can still play in ladder mode."""
        try:
            prompt_hash = self.compute_prompt_hash()
            resp = self.http.post(
                f"{self.base_url}/api/v1/agents/{self.agent_id}/register-prompt",
                json={
                    "season_id": season_id,
                    "prompt_name": self.prompt_name,
                    "prompt_hash": prompt_hash,
                }
            )
            if resp.status_code == 200:
                print(f"[COMPLIANCE] Registered prompt for season {season_id}")
                return True
            else:
                print(f"[COMPLIANCE] Registration skipped ({resp.status_code}): playing in ladder mode")
                return False
        except Exception as e:
            print(f"[COMPLIANCE] Registration skipped ({e}): playing in ladder mode")
            return False

    def verify_prompt(self) -> bool:
        """Verify prompt hash matches registered hash for season games.

        Returns True for ladder games (no active season) or valid season verification.
        Returns False only if there's an explicit hash mismatch in a season game."""
        try:
            prompt_hash = self.compute_prompt_hash()
            resp = self.http.post(
                f"{self.base_url}/api/v1/agents/{self.agent_id}/verify-prompt",
                json={"prompt_hash": prompt_hash}
            )
            if resp.status_code == 200:
                result = resp.json()
                mode = result.get("mode", "unknown")
                if mode == "ladder":
                    return True  # Ladder mode allows all prompts
                return True  # Season mode: hash verified
            elif resp.status_code == 403:
                # Explicit hash mismatch - fail the order
                print(f"[COMPLIANCE] Verification failed (hash mismatch): {resp.text}")
                return False
            else:
                # Other errors (e.g., not registered) - allow in ladder mode
                print(f"[COMPLIANCE] Verification warning: {resp.text} (ladder mode allowed)")
                return True
        except Exception as e:
            print(f"[COMPLIANCE] Verification warning: {e} (ladder mode allowed)")
            return True

    def call_ollama(self, prompt: str) -> str:
        resp = self.ollama_http.post(
            f"{self.ollama_url}/api/generate",
            json={
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def decide_orders(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        my_units = self.get_owned_units(state["map"])
        if not my_units:
            return []

        adjacency = state.get("adjacency", {})
        supply_centers = state.get("supply_centers", [])
        game_map = state["map"]

        unit_briefs = []
        for terr in my_units:
            neighbors = adjacency.get(terr, [])
            neighbor_notes = []
            for n in neighbors:
                n_data = game_map.get(n, {})
                owner = n_data.get("sc_owner")
                if n in supply_centers and owner is None:
                    # Highlight vacated SCs (just became empty)
                    if n in self.vacated_scs:
                        neighbor_notes.append(f"{n} (VACATED supply center - just abandoned, grab it now!)")
                    else:
                        neighbor_notes.append(f"{n} (EMPTY supply center - capturing it scores a point)")
                elif n in supply_centers and owner == self.faction:
                    neighbor_notes.append(f"{n} (your own supply center)")
                elif n in supply_centers:
                    neighbor_notes.append(f"{n} (enemy-held supply center, owned by {owner})")
                else:
                    neighbor_notes.append(f"{n} (not a supply center)")
            unit_briefs.append(f"- Unit at {terr} can MOVE to: {'; '.join(neighbor_notes)}")

        enemy_factions = [f for f in ("Red", "Blue", "Green", "Yellow") if f != self.faction]
        vacated_note = f"VACATED supply centers (just abandoned): {', '.join(self.vacated_scs)}" if self.vacated_scs else "No vacated supply centers this turn."
        prompt = string.Template(self.prompts["orders"]).safe_substitute(
            faction=self.faction,
            unit_briefs="\n".join(unit_briefs),
            my_units=my_units,
            enemy_factions=", ".join(enemy_factions),
            vacated_scs=vacated_note,
        )
        orders: List[Dict[str, Any]] = []
        try:
            raw = self.call_ollama(prompt)
            data = json.loads(raw)
            orders = data.get("orders", [])
        except Exception as e:
            print(f"[LLM] order decision failed ({e}), defaulting to HOLD")

        return self._validate_orders(orders, my_units, adjacency)

    def _validate_orders(
        self, orders: List[Dict[str, Any]], my_units: List[str], adjacency: Dict[str, List[str]]
    ) -> List[Dict[str, Any]]:
        valid: List[Dict[str, Any]] = []
        seen = set()
        for o in orders:
            terr = o.get("unit_territory")
            if terr not in my_units or terr in seen:
                continue
            if o.get("action") == "MOVE":
                dest = o.get("target_destination")
                if dest and dest in adjacency.get(terr, []):
                    valid.append({"unit_territory": terr, "action": "MOVE", "target_destination": dest})
                    seen.add(terr)
                    continue
            if o.get("action") == "SPY":
                target = o.get("target_faction")
                if target and target != self.faction and target in ("Red", "Blue", "Green", "Yellow"):
                    valid.append({"unit_territory": terr, "action": "SPY", "target_faction": target})
                    seen.add(terr)
                    continue
            # Unknown/invalid action or bad MOVE/SPY target - fall back to HOLD.
            valid.append({"unit_territory": terr, "action": "HOLD"})
            seen.add(terr)

        for u in my_units:
            if u not in seen:
                valid.append({"unit_territory": u, "action": "HOLD"})
        return valid

    def decide_message(self, state: Dict[str, Any]) -> Optional[Dict[str, str]]:
        pending_treaties = self.get_pending_treaties()
        pending_summary = "; ".join(
            f"{t['treaty_id']} from {t['initiator']}: {t['treaty_type']} over {t['target_territories']} "
            f"for {t['duration_turns']} turns"
            for t in pending_treaties
        ) or "none"

        prompt = string.Template(self.prompts["message"]).safe_substitute(
            faction=self.faction,
            turn=state["turn"],
            map=json.dumps(state["map"]),
            scores=json.dumps(state["scores"]),
            pending_treaties=pending_summary,
        )
        try:
            raw = self.call_ollama(prompt)
            data = json.loads(raw)
        except Exception as e:
            print(f"[LLM] message decision failed ({e})")
            return None

        proposal = data.get("propose_treaty")
        if isinstance(proposal, dict) and proposal.get("signatory") in ("Red", "Blue", "Green", "Yellow") and proposal["signatory"] != self.faction:
            try:
                self.propose_treaty(
                    signatory=proposal["signatory"],
                    treaty_type=str(proposal.get("treaty_type", "NON_AGGRESSION")),
                    target_territories=list(proposal.get("target_territories", [])),
                    duration_turns=int(proposal.get("duration_turns", 5)),
                )
            except Exception as e:
                print(f"[{self.faction}] Treaty proposal failed: {e}")

        sign_id = data.get("sign_treaty_id")
        if sign_id and any(t["treaty_id"] == sign_id for t in pending_treaties):
            try:
                self.sign_treaty(sign_id)
            except Exception as e:
                print(f"[{self.faction}] Treaty sign failed: {e}")

        if data.get("send") and data.get("content"):
            return {"recipient": "PUBLIC", "content": str(data["content"])[:200]}
        return None

    def run(self) -> None:
        self.register_agent()

        # Try to register prompt for current tournament season
        try:
            # Get current season (we'll try a reasonable season ID)
            # In practice, the server would return the active season
            # For now, bots can use a fixed season or the server will reject
            self.register_prompt_for_season("season_1")
        except Exception as e:
            print(f"[COMPLIANCE] Warning: could not register prompt: {e}")

        while True:
            self.join_queue()
            print(f"\n[START] Game started for {self.faction} in {self.game_id}\n")

            while True:
                try:
                    state = self.get_game_state()
                    if state["phase"] == "FINISHED":
                        print(f"\n[GAME OVER] Winner: {state.get('winner')}\n")
                        break

                    if state["phase"] == "DIPLOMACY" and self.last_diplomacy_turn < state["turn"]:
                        msg = self.decide_message(state)
                        if msg:
                            self.send_message(msg["recipient"], msg["content"])
                        self.last_diplomacy_turn = state["turn"]

                    if state["phase"] == "ORDERS" and self.last_orders_turn < state["turn"]:
                        print(f"[Turn {state['turn']}] ORDERS PHASE")
                        # Detect supply centers vacated in the previous turn
                        self.detect_vacated_scs(state["map"])
                        orders = self.decide_orders(state)
                        if orders:
                            self.submit_orders(orders)
                        self.last_orders_turn = state["turn"]

                except Exception as e:
                    print(f"[ERROR] {e}")

                time.sleep(3.0)

            print(f"[TOURNAMENT] Re-queueing...\n")
            self.game_id = None
            self.faction = None
            self.last_orders_turn = 0
            self.last_diplomacy_turn = 0
            time.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-name", default="OllamaBot")
    parser.add_argument("--developer-handle", default="dev")
    parser.add_argument("--model", default="mistral")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--prompts-file", default="prompts.yaml", help="YAML file of named prompt variants")
    parser.add_argument("--prompt-name", default="default", help="Which variant in --prompts-file to use")

    args = parser.parse_args()

    bot = OllamaBot(
        base_url=args.base_url,
        agent_name=args.agent_name,
        developer_handle=args.developer_handle,
        ollama_model=args.model,
        ollama_url=args.ollama_url,
        prompts_file=args.prompts_file,
        prompt_name=args.prompt_name,
    )
    bot.run()
