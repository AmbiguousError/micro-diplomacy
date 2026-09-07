import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from .db import init_db, load_all_game_states, save_game_state
from .gauntlet_router import router as gauntlet_router
from .mcts import Adjudicator, FACTIONS, Order, Phase, STARTING_POSITIONS, SUPPLY_CENTERS, TerritoryState, GameState, ADJACENCY

# =====================================================================
# MODELS & GAME LOOP
# =====================================================================

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

class GameSession:
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.turn = 1
        self.phase = Phase.DIPLOMACY
        self.time_remaining = 120
        self.winner: Optional[str] = None
        self.messages: List[Message] = []
        self.orders: Dict[str, List[Order]] = {f: [] for f in FACTIONS}
        self.recent_events: List[str] = ["Game started."]
        
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

    def to_state(self) -> Dict[str, Any]:
        """Serializes this session to a JSON-safe dict for persistence."""
        return {
            "turn": self.turn,
            "phase": self.phase.value,
            "time_remaining": self.time_remaining,
            "winner": self.winner,
            "messages": [m.model_dump() for m in self.messages],
            "orders": {f: [o.model_dump() for o in orders] for f, orders in self.orders.items()},
            "recent_events": self.recent_events,
            "map": {terr: ts.model_dump() for terr, ts in self.map.items()},
        }

    def restore(self, state: Dict[str, Any]) -> None:
        """Overwrites this session's state from a dict produced by to_state()."""
        self.turn = state["turn"]
        self.phase = Phase(state["phase"])
        self.time_remaining = state["time_remaining"]
        self.winner = state.get("winner")
        self.messages = [Message(**m) for m in state.get("messages", [])]
        self.orders = {f: [Order(**o) for o in orders] for f, orders in state.get("orders", {}).items()}
        self.recent_events = state.get("recent_events", [])
        self.map = {terr: TerritoryState(**ts) for terr, ts in state.get("map", {}).items()}

# =====================================================================
# FASTAPI APPLICATION & ENDPOINTS
# =====================================================================

games: Dict[str, GameSession] = {}

async def game_loop(game_id: str):
    while True:
        await asyncio.sleep(1)
        game = games.get(game_id)
        if not game or game.phase == Phase.FINISHED:
            break
        game.time_remaining -= 1
        if game.time_remaining <= 0:
            game.step_phase()
            await save_game_state(game_id, game.to_state())

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    for game_id, state in (await load_all_game_states()).items():
        game = GameSession(game_id)
        game.restore(state)
        games[game_id] = game
        if game.phase != Phase.FINISHED:
            asyncio.create_task(game_loop(game_id))
    yield

app = FastAPI(title="Micro-Diplomacy Server", version="1.0", lifespan=lifespan)
app.include_router(gauntlet_router)

def authenticate_agent(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Bearer token.")
    faction = authorization.replace("Bearer ", "").strip()
    if faction not in FACTIONS:
        raise HTTPException(status_code=403, detail=f"Invalid faction key. Must be one of {FACTIONS}")
    return faction

@app.post("/api/v1/games", status_code=201)
async def create_game(background_tasks: BackgroundTasks):
    game_id = f"game_{len(games) + 1001}"
    game = GameSession(game_id)
    games[game_id] = game
    await save_game_state(game_id, game.to_state())
    background_tasks.add_task(game_loop, game_id)
    return {"game_id": game_id, "status": "CREATED"}

@app.get("/api/v1/games/{game_id}/state", response_model=GameState)
def get_state(game_id: str):
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return GameState(
        game_id=game.game_id,
        turn=game.turn,
        phase=game.phase,
        time_remaining_seconds=game.time_remaining,
        map=game.map,
        scores=game.calculate_scores(),
        winner=game.winner,
        recent_events=game.recent_events,
    )

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
    await save_game_state(game_id, game.to_state())
    return {"message_id": message_obj.id, "status": "DELIVERED"}

@app.get("/api/v1/games/{game_id}/messages")
def read_messages(game_id: str, since_turn: int = 1, faction: str = Header(..., alias="Authorization")):
    agent_faction = authenticate_agent(faction)
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    visible_messages = [
        m for m in game.messages
        if m.turn >= since_turn and (
            m.recipient == "PUBLIC" or m.recipient == agent_faction or m.sender == agent_faction
        )
    ]
    return {"messages": visible_messages}

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
    await save_game_state(game_id, game.to_state())
    return {"status": "ACCEPTED", "turn": game.turn, "order_count": len(orders)}

# Mounted last so it only catches paths none of the /api/v1/... routes above
# matched - e.g. GET /spectator.html or / (index.html). Root-mounted (not
# under /static) to match streamer.sh's hardcoded
# http://localhost:8000/spectator.html and player.html's root-relative
# API_BASE fetches.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
