import asyncio
import random
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import server_hub
from .archetypes import MachiavellianTraitor, OpportunisticGreedy, PacifistTurtle, StochasticChaos
from .db import init_db, load_all_game_states, save_game_state
from .dual_caster import DualShoutcasterService
from .gauntlet_router import router as gauntlet_router
from .mcts import Adjudicator, FACTIONS, Order, Phase, STARTING_POSITIONS, SUPPLY_CENTERS, TerritoryState, GameState, ADJACENCY, SimState

ARCHETYPE_CLASSES = {
    "PacifistTurtle": PacifistTurtle,
    "OpportunisticGreedy": OpportunisticGreedy,
    "MachiavellianTraitor": MachiavellianTraitor,
    "StochasticChaos": StochasticChaos,
}

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
        self.caster_script: List[Dict[str, str]] = []
        # Non-empty only for practice matches (POST /api/v1/practice):
        # faction -> archetype class name, for factions controlled by a
        # built-in bot instead of a real registered agent.
        self.bot_factions: Dict[str, str] = {}

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

    def run_bot_diplomacy(self):
        """Has every bot faction generate and post its diplomacy messages
        for the current turn. Called once per turn, at DIPLOMACY start."""
        if not self.bot_factions:
            return
        sim_state = SimState.from_territory_map(self.map, self.turn)
        for faction, archetype_name in self.bot_factions.items():
            bot = ARCHETYPE_CLASSES[archetype_name](faction)
            for msg in bot.generate_messages(self.turn, sim_state):
                self.messages.append(Message(
                    id=f"msg_{len(self.messages) + 1}",
                    turn=self.turn,
                    sender=faction,
                    recipient=msg["recipient"],
                    content=msg["content"],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))

    def run_bot_orders(self):
        """Has every bot faction generate its orders for the current turn,
        so they're already present in self.orders before the real ORDERS
        timer elapses and resolve_turn() reads it. Called once per turn,
        at ORDERS start."""
        if not self.bot_factions:
            return
        sim_state = SimState.from_territory_map(self.map, self.turn)
        for faction, archetype_name in self.bot_factions.items():
            bot = ARCHETYPE_CLASSES[archetype_name](faction)
            self.orders[faction] = bot.generate_orders(self.turn, sim_state)

    def step_phase(self):
        if self.phase == Phase.DIPLOMACY:
            self.phase = Phase.ORDERS
            self.time_remaining = 30
            self.run_bot_orders()
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
        self.run_bot_diplomacy()

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
            "bot_factions": self.bot_factions,
            "caster_script": self.caster_script,
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
        self.bot_factions = state.get("bot_factions", {})
        self.caster_script = state.get("caster_script", [])
        self.recent_events = state.get("recent_events", [])
        self.map = {terr: TerritoryState(**ts) for terr, ts in state.get("map", {}).items()}

# =====================================================================
# FASTAPI APPLICATION & ENDPOINTS
# =====================================================================

games: Dict[str, GameSession] = {}
caster_service = DualShoutcasterService()

async def update_caster_script(game: GameSession) -> None:
    """Generates this turn's caster commentary via an LLM call and stores it
    on the session. Text only - there's no synthesized audio (Piper TTS
    isn't wired in) and no push delivery (see GET .../state's caster_script
    field instead). Any failure (no/invalid OPENAI_API_KEY, network error,
    malformed LLM output) is caught here so a bad turn of commentary can
    never break the actual game loop - it just leaves caster_script empty."""
    try:
        game.caster_script = await caster_service.generate_broadcast_script(
            turn=game.turn,
            combat=game.recent_events,
            breaches=[],  # treaty breaches aren't wired into resolution yet - see TODO.md
            state={"map": {t: s.model_dump() for t, s in game.map.items()}},
            match_history_summary="",
        )
    except Exception as e:
        print(f"[dual_caster] commentary generation failed: {e}")
        game.caster_script = []

async def game_loop(game_id: str):
    while True:
        await asyncio.sleep(1)
        game = games.get(game_id)
        if not game or game.phase == Phase.FINISHED:
            break
        game.time_remaining -= 1
        if game.time_remaining <= 0:
            was_orders_phase = game.phase == Phase.ORDERS
            game.step_phase()
            if was_orders_phase:
                await update_caster_script(game)
            await save_game_state(game_id, game.to_state())

async def spawn_game(game_id: str) -> GameSession:
    """Creates and persists a new GameSession, and starts its game_loop task.
    Shared by the direct create-game endpoint and the matchmaker callback."""
    game = GameSession(game_id)
    games[game_id] = game
    await save_game_state(game_id, game.to_state())
    asyncio.create_task(game_loop(game_id))
    return game

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    for game_id, state in (await load_all_game_states()).items():
        game = GameSession(game_id)
        game.restore(state)
        games[game_id] = game
        if game.phase != Phase.FINISHED:
            asyncio.create_task(game_loop(game_id))
    asyncio.create_task(server_hub.matchmaker_worker(spawn_game))
    yield

app = FastAPI(title="Micro-Diplomacy Server", version="1.0", lifespan=lifespan)
app.include_router(gauntlet_router)
app.include_router(server_hub.router)

def get_authorized_faction(game_id: str, agent: server_hub.AgentRecord = Depends(server_hub.authenticate_agent)) -> str:
    """
    Auth for all per-game agent actions (messages, orders): the Authorization
    header must be a real agent API key (see server_hub.authenticate_agent),
    and that agent must have actually been matchmade into *this* game_id -
    replaces the old scheme where the faction name itself was the credential.
    """
    match = server_hub.assigned_matches.get(agent.agent_id)
    if not match or match["game_id"] != game_id:
        raise HTTPException(status_code=403, detail="Your agent is not assigned to this game.")
    return match["faction"]

@app.post("/api/v1/games", status_code=201)
async def create_game():
    game_id = f"game_{len(games) + 1001}"
    await spawn_game(game_id)
    return {"game_id": game_id, "status": "CREATED"}

@app.get("/api/v1/games")
def list_games():
    """Lightweight summary of every game currently held in memory, public
    like GET .../state (no auth) - lets a spectator see what's running
    without needing to already know a game_id."""
    return {
        "games": [
            {
                "game_id": g.game_id,
                "turn": g.turn,
                "phase": g.phase,
                "scores": g.calculate_scores(),
                "winner": g.winner,
                "is_practice": bool(g.bot_factions),
            }
            for g in games.values()
        ]
    }

@app.post("/api/v1/practice")
async def start_practice_match(agent: server_hub.AgentRecord = Depends(server_hub.authenticate_agent)):
    """
    Starts a real GameSession immediately, filling the other 3 factions
    with built-in archetype bots (app/archetypes.py) instead of waiting
    for 3 more real agents in the matchmaking queue - see TODO.md: there's
    no way to leave that queue once joined, and matches only form once 4
    real agents are waiting, so a solo visitor previously had no way to
    actually experience a game. Reuses server_hub.assigned_matches (the
    same structure the real matchmaker populates) so every existing
    per-game auth/messages/orders code path works unchanged.
    """
    existing = server_hub.assigned_matches.get(agent.agent_id)
    if existing:
        existing_game = games.get(existing["game_id"])
        was_finished_practice = (
            existing_game and existing_game.bot_factions and existing_game.phase == Phase.FINISHED
        )
        if not was_finished_practice:
            raise HTTPException(status_code=409, detail="Your agent is already assigned to a game.")

    game_id = f"practice_{secrets.token_hex(4)}"
    factions_shuffled = FACTIONS.copy()
    random.shuffle(factions_shuffled)
    human_faction = factions_shuffled[0]
    bot_faction_names = factions_shuffled[1:]

    game = await spawn_game(game_id)
    game.bot_factions = {f: random.choice(list(ARCHETYPE_CLASSES.keys())) for f in bot_faction_names}
    game.run_bot_diplomacy()
    await save_game_state(game_id, game.to_state())

    server_hub.assigned_matches[agent.agent_id] = {
        "game_id": game_id,
        "faction": human_faction,
        "timestamp": time.time(),
    }
    return {"status": "MATCH_FOUND", "game_id": game_id, "assigned_faction": human_faction}

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
        caster_script=game.caster_script,
        bot_factions=game.bot_factions,
    )

@app.post("/api/v1/games/{game_id}/messages", status_code=201)
async def send_message(game_id: str, msg: MessageCreate, agent_faction: str = Depends(get_authorized_faction)):
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
def read_messages(game_id: str, since_turn: int = 1, agent_faction: str = Depends(get_authorized_faction)):
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
async def submit_orders(game_id: str, payload: Dict[str, List[Order]], agent_faction: str = Depends(get_authorized_faction)):
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
