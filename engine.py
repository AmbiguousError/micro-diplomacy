"""
Micro-Diplomacy WebSocket Engine & Adjudication Server
Framework: FastAPI + WebSockets + Pydantic + AsyncIO
Run: uvicorn engine:app --reload --port 8000
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from fastapi import FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

# =====================================================================
# 1. MAP TOPOLOGY & CONSTANTS
# =====================================================================

FACTIONS = ["Red", "Blue", "Green", "Yellow"]

ADJACENCY: Dict[str, Set[str]] = {
    "Northreach": {"Ironpeaks", "Westmarch", "Centerlands"},
    "Ironpeaks": {"Northreach", "Centerlands", "Eastgate"},
    "Westmarch": {"Northreach", "Centerlands", "Sunport", "Southvale"},
    "Centerlands": {"Northreach", "Ironpeaks", "Westmarch", "Eastgate", "Southvale"},
    "Eastgate": {"Ironpeaks", "Centerlands", "Southvale", "Duneport"},
    "Sunport": {"Westmarch", "Southvale"},
    "Southvale": {"Westmarch", "Centerlands", "Eastgate", "Sunport", "Duneport"},
    "Duneport": {"Eastgate", "Southvale"},
}

SUPPLY_CENTERS: Set[str] = {
    "Northreach", "Ironpeaks", "Centerlands", "Sunport", "Southvale", "Duneport"
}

STARTING_POSITIONS: Dict[str, str] = {
    "Red": "Northreach",
    "Blue": "Ironpeaks",
    "Green": "Sunport",
    "Yellow": "Duneport",
}

# =====================================================================
# 2. WEBSOCKET CONNECTION MANAGER
# =====================================================================

class ConnectionManager:
    """Manages active WebSocket channels per game for spectators."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, game_id: str, websocket: WebSocket):
        await websocket.accept()
        if game_id not in self.active_connections:
            self.active_connections[game_id] = set()
        self.active_connections[game_id].add(websocket)

    def disconnect(self, game_id: str, websocket: WebSocket):
        if game_id in self.active_connections:
            self.active_connections[game_id].discard(websocket)
            if not self.active_connections[game_id]:
                del self.active_connections[game_id]

    async def broadcast(self, game_id: str, message: dict):
        if game_id not in self.active_connections:
            return
        dead_connections = set()
        for websocket in self.active_connections[game_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                dead_connections.add(websocket)

        for dead_ws in dead_connections:
            self.active_connections[game_id].discard(dead_ws)


manager = ConnectionManager()

# =====================================================================
# 3. DATA MODELS
# =====================================================================

class Phase(str, Enum):
    WAITING = "WAITING"
    DIPLOMACY = "DIPLOMACY"
    ORDERS = "ORDERS"
    RESOLVED = "RESOLVED"
    FINISHED = "FINISHED"

class ActionType(str, Enum):
    HOLD = "HOLD"
    MOVE = "MOVE"
    SUPPORT = "SUPPORT"

class Order(BaseModel):
    unit_territory: str
    action: ActionType
    target_destination: Optional[str] = None
    target_faction: Optional[str] = None
    target_source: Optional[str] = None

class MessageCreate(BaseModel):
    recipient: str
    content: str

class Message(BaseModel):
    id: str
    turn: int
    sender: str
    recipient: str
    content: str
    timestamp: str

class TerritoryState(BaseModel):
    sc_owner: Optional[str] = None
    unit_faction: Optional[str] = None

# =====================================================================
# 4. ADJUDICATION ENGINE
# =====================================================================

class Adjudicator:
    @staticmethod
    def adjudicate(
        current_map: Dict[str, TerritoryState],
        submitted_orders: Dict[str, List[Order]]
    ) -> Tuple[Dict[str, TerritoryState], List[str]]:
        events: List[str] = []
        new_map: Dict[str, TerritoryState] = {
            t: TerritoryState(sc_owner=state.sc_owner, unit_faction=None)
            for t, state in current_map.items()
        }

        active_orders: Dict[str, Tuple[str, Order]] = {}
        for faction, orders in submitted_orders.items():
            for order in orders:
                terr = order.unit_territory
                if current_map[terr].unit_faction == faction:
                    active_orders[terr] = (faction, order)

        for terr, state in current_map.items():
            if state.unit_faction and terr not in active_orders:
                active_orders[terr] = (
                    state.unit_faction,
                    Order(unit_territory=terr, action=ActionType.HOLD)
                )

        uncut_supports: Set[str] = set()
        for terr, (faction, order) in active_orders.items():
            if order.action == ActionType.SUPPORT:
                dest = order.target_destination
                is_cut = False
                for other_terr, (_, other_order) in active_orders.items():
                    if (
                        other_order.action == ActionType.MOVE
                        and other_order.target_destination == terr
                        and other_terr != dest
                    ):
                        is_cut = True
                        events.append(f"Support from {terr} was CUT by attack from {other_terr}.")
                        break
                if not is_cut:
                    uncut_supports.add(terr)

        incoming_attacks: Dict[str, List[Tuple[str, str, int]]] = {t: [] for t in ADJACENCY}
        holds: Dict[str, Tuple[str, int]] = {}

        for terr, (faction, order) in active_orders.items():
            if order.action == ActionType.MOVE:
                dest = order.target_destination
                if dest in ADJACENCY.get(terr, set()):
                    support_bonus = sum(
                        1 for s_terr in uncut_supports
                        if active_orders[s_terr][1].target_source == terr
                        and active_orders[s_terr][1].target_destination == dest
                    )
                    incoming_attacks[dest].append((terr, faction, 1 + support_bonus))
                else:
                    events.append(f"Invalid move: {terr} not adjacent to {dest}. Defaulted to HOLD.")
                    holds[terr] = (faction, 1)

            elif order.action in (ActionType.HOLD, ActionType.SUPPORT):
                support_bonus = sum(
                    1 for s_terr in uncut_supports
                    if active_orders[s_terr][1].target_source == terr
                    and active_orders[s_terr][1].target_destination == terr
                )
                holds[terr] = (faction, 1 + support_bonus)

        surviving_units: Dict[str, str] = {}

        for dest in ADJACENCY:
            attacks = incoming_attacks[dest]
            has_holder = dest in holds

            if not attacks:
                if has_holder:
                    surviving_units[dest] = holds[dest][0]
                continue

            attacks.sort(key=lambda x: x[2], reverse=True)
            max_attack_str = attacks[0][2]
            tied_attacks = [atk for atk in attacks if atk[2] == max_attack_str]

            if len(tied_attacks) > 1:
                events.append(f"Bounce at {dest}: Collision at strength {max_attack_str}.")
                if has_holder:
                    surviving_units[dest] = holds[dest][0]
                for atk_terr, _, _ in attacks:
                    surviving_units[atk_terr] = active_orders[atk_terr][0]
                continue

            winner_terr, winner_faction, win_str = attacks[0]

            head_to_head_fail = False
            if active_orders.get(dest, (None, None))[1]:
                dest_order = active_orders[dest][1]
                if dest_order.action == ActionType.MOVE and dest_order.target_destination == winner_terr:
                    opp_attacks = [a for a in incoming_attacks[winner_terr] if a[0] == dest]
                    if opp_attacks:
                        opp_str = opp_attacks[0][2]
                        if win_str <= opp_str:
                            head_to_head_fail = True
                            events.append(f"Head-to-head bounce between {winner_terr} and {dest}.")
                            surviving_units[winner_terr] = winner_faction
                            surviving_units[dest] = active_orders[dest][0]

            if head_to_head_fail:
                continue

            if has_holder:
                def_faction, def_str = holds[dest]
                if win_str > def_str:
                    events.append(f"{winner_faction} dislodged {def_faction} at {dest} ({win_str} vs {def_str}).")
                    surviving_units[dest] = winner_faction
                else:
                    events.append(f"{def_faction} held {dest} against {winner_faction} ({def_str} vs {win_str}).")
                    surviving_units[dest] = def_faction
                    surviving_units[winner_terr] = winner_faction
            else:
                events.append(f"{winner_faction} moved from {winner_terr} to {dest} successfully.")
                surviving_units[dest] = winner_faction

        for terr, faction in surviving_units.items():
            new_map[terr].unit_faction = faction
            if terr in SUPPLY_CENTERS:
                new_map[terr].sc_owner = faction

        return new_map, events

# =====================================================================
# 5. GAME SESSION
# =====================================================================

class GameSession:
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.turn = 1
        self.phase = Phase.DIPLOMACY
        self.time_remaining = 120
        self.winner: Optional[str] = None
        self.messages: List[Message] = []
        self.orders: Dict[str, List[Order]] = {f: [] for f in FACTIONS}
        self.recent_events: List[str] = ["Match initiated. Turn 1 Diplomacy open."]

        self.map: Dict[str, TerritoryState] = {
            t: TerritoryState(sc_owner=None, unit_faction=None) for t in ADJACENCY
        }
        for faction, start_terr in STARTING_POSITIONS.items():
            self.map[start_terr].unit_faction = faction
            self.map[start_terr].sc_owner = faction

    def calculate_scores(self) -> Dict[str, int]:
        scores = {f: 0 for f in FACTIONS}
        for terr, state in self.map.items():
            if terr in SUPPLY_CENTERS and state.sc_owner in scores:
                scores[state.sc_owner] += 1
        return scores

    def to_dict(self) -> Dict[str, Any]:
        return {
            "game_id": self.game_id,
            "turn": self.turn,
            "phase": self.phase.value,
            "time_remaining_seconds": self.time_remaining,
            "map": {k: v.model_dump() for k, v in self.map.items()},
            "scores": self.calculate_scores(),
            "winner": self.winner,
            "recent_events": self.recent_events,
        }

    def step_phase(self):
        if self.phase == Phase.DIPLOMACY:
            self.phase = Phase.ORDERS
            self.time_remaining = 30
        elif self.phase == Phase.ORDERS:
            self.resolve_turn()

    def resolve_turn(self):
        new_map, events = Adjudicator.adjudicate(self.map, self.orders)
        self.map = new_map
        self.recent_events = events
        self.orders = {f: [] for f in FACTIONS}

        scores = self.calculate_scores()
        for faction, sc_count in scores.items():
            if sc_count >= 5:
                self.winner = faction
                self.phase = Phase.FINISHED
                return

        if self.turn >= 10:
            top_score = max(scores.values())
            winners = [f for f, s in scores.items() if s == top_score]
            self.winner = "/".join(winners)
            self.phase = Phase.FINISHED
            return

        self.turn += 1
        self.phase = Phase.DIPLOMACY
        self.time_remaining = 120

# =====================================================================
# 6. APP SETUP & WEBSOCKET TICKER
# =====================================================================

app = FastAPI(title="Micro-Diplomacy WS Engine", version="2.0")
games: Dict[str, GameSession] = {}

async def game_loop(game_id: str):
    """Async background loop broadcasting state/timer events over WS."""
    while True:
        await asyncio.sleep(1)
        game = games.get(game_id)
        if not game or game.phase == Phase.FINISHED:
            if game and game.phase == Phase.FINISHED:
                await manager.broadcast(game_id, {"type": "GAME_OVER", "payload": game.to_dict()})
            break

        game.time_remaining -= 1

        if game.time_remaining <= 0:
            game.step_phase()
            await manager.broadcast(game_id, {"type": "STATE_UPDATE", "payload": game.to_dict()})
        else:
            await manager.broadcast(
                game_id,
                {
                    "type": "TIMER_TICK",
                    "payload": {
                        "time_remaining_seconds": game.time_remaining,
                        "phase": game.phase.value,
                        "turn": game.turn,
                    },
                },
            )

def authenticate_agent(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    faction = authorization.replace("Bearer ", "").strip()
    if faction not in FACTIONS:
        raise HTTPException(status_code=403, detail="Invalid faction key.")
    return faction

# =====================================================================
# 7. ENDPOINTS & WEBSOCKET ROUTE
# =====================================================================

@app.post("/api/v1/games", status_code=201)
async def create_game():
    game_id = f"game_{len(games) + 1001}"
    game = GameSession(game_id)
    games[game_id] = game
    asyncio.create_task(game_loop(game_id))
    return {"game_id": game_id, "status": "CREATED"}

@app.websocket("/ws/games/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    """Spectator WebSocket channel for real-time state, ticks, and chat."""
    game = games.get(game_id)
    if not game:
        await websocket.close(code=4004, reason="Game session not found")
        return

    await manager.connect(game_id, websocket)
    await websocket.send_json({"type": "INIT_STATE", "payload": game.to_dict(), "messages": [m.model_dump() for m in game.messages]})

    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(game_id, websocket)

@app.post("/api/v1/games/{game_id}/messages", status_code=201)
async def send_message(game_id: str, msg: MessageCreate, faction: str = Header(..., alias="Authorization")):
    agent_faction = authenticate_agent(faction)
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.phase != Phase.DIPLOMACY:
        raise HTTPException(status_code=400, detail="Messages only accepted during DIPLOMACY phase")

    message_obj = Message(
        id=f"msg_{len(game.messages) + 1}",
        turn=game.turn,
        sender=agent_faction,
        recipient=msg.recipient,
        content=msg.content,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    game.messages.append(message_obj)
    await manager.broadcast(game_id, {"type": "NEW_MESSAGE", "payload": message_obj.model_dump()})
    return {"message_id": message_obj.id, "status": "DELIVERED"}

@app.post("/api/v1/games/{game_id}/orders")
async def submit_orders(game_id: str, payload: Dict[str, List[Order]], faction: str = Header(..., alias="Authorization")):
    agent_faction = authenticate_agent(faction)
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.phase != Phase.ORDERS:
        raise HTTPException(status_code=400, detail="Orders only accepted during ORDERS phase")

    orders = payload.get("orders", [])
    game.orders[agent_faction] = orders

    await manager.broadcast(
        game_id,
        {"type": "ORDER_SUBMITTED", "payload": {"faction": agent_faction, "order_count": len(orders)}},
    )
    return {"status": "ACCEPTED", "turn": game.turn, "order_count": len(orders)}
