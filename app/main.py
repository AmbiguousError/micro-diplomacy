import asyncio
import random
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import server_hub
from .archetypes import MachiavellianTraitor, OpportunisticGreedy, PacifistTurtle, StochasticChaos
from .db import (
    delete_assigned_match,
    init_db,
    load_all_agent_states,
    load_all_assigned_matches,
    load_all_game_states,
    save_agent_state,
    save_assigned_match,
    save_game_state,
)
from .dual_caster import DualShoutcasterService
from .gauntlet_router import router as gauntlet_router
from .mcts import (
    Adjudicator,
    CLASSIC_TOPOLOGY,
    FACTIONS,
    GameState,
    MapTopology,
    Order,
    Phase,
    SimState,
    TerritoryState,
    build_generated_topology,
)
from .treaties_engine import TreatyAndEspionageEngine, TreatyType
from .trueskill_engine import BayesianMMREngine, MatchResultSnapshot, TrueSkillProfile

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

class TreatyProposal(BaseModel):
    signatory: str
    treaty_type: str  # "NON_AGGRESSION" | "DMZ" | "SUPPORT_PROMISE"
    target_territories: List[str]
    duration_turns: int = 5

class GameSession:
    def __init__(self, game_id: str, topology: MapTopology = CLASSIC_TOPOLOGY, map_mode: str = "fixed"):
        self.game_id = game_id
        self.topology = topology
        self.map_mode = map_mode
        self.turn = 1
        self.phase = Phase.DIPLOMACY
        self.time_remaining = 30
        self.winner: Optional[str] = None
        self.messages: List[Message] = []
        self.orders: Dict[str, List[Order]] = {f: [] for f in FACTIONS}
        self.recent_events: List[str] = ["Game started."]
        self.caster_script: List[Dict[str, str]] = []
        # Non-empty only for practice matches (POST /api/v1/practice):
        # faction -> archetype class name, for factions controlled by a
        # built-in bot instead of a real registered agent.
        self.bot_factions: Dict[str, str] = {}
        self.treaty_engine = TreatyAndEspionageEngine()
        # Intel packets from resolved SPY orders (app/treaties_engine.py's
        # resolve_espionage_orders) - kept server-side only, never exposed
        # via the public GET .../state; see GET .../intel, which filters to
        # the requesting agent's own spying_faction.
        self.intel_reports: List[Dict[str, Any]] = []

        self.map: Dict[str, TerritoryState] = {
            t: TerritoryState(sc_owner=None, unit_faction=None) for t in topology.territories
        }
        for faction, start_terr in topology.starting_positions.items():
            self.map[start_terr].unit_faction = faction
            self.map[start_terr].sc_owner = faction

    def calculate_scores(self) -> Dict[str, int]:
        scores = {f: 0 for f in FACTIONS}
        for terr, state in self.map.items():
            if terr in self.topology.supply_centers and state.sc_owner in scores:
                scores[state.sc_owner] += 1
        return scores

    def run_bot_diplomacy(self):
        """Has every bot faction generate and post its diplomacy messages
        for the current turn. Called once per turn, at DIPLOMACY start."""
        if not self.bot_factions:
            return
        sim_state = SimState.from_territory_map(self.map, self.turn, topology=self.topology)
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
        sim_state = SimState.from_territory_map(self.map, self.turn, topology=self.topology)
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
        orders_as_dicts = {f: [o.model_dump() for o in orders] for f, orders in self.orders.items()}
        breach_events = self.treaty_engine.evaluate_orders_for_breaches(self.turn, orders_as_dicts)

        turn_messages = [m.model_dump() for m in self.messages]
        new_intel = self.treaty_engine.resolve_espionage_orders(self.turn, orders_as_dicts, turn_messages)
        self.intel_reports.extend(new_intel)
        espionage_events = [
            f"🕵️ {p['spying_faction']} ran an espionage operation against {p['target_faction']}."
            for p in new_intel
        ]

        new_map, events = Adjudicator.adjudicate(
            self.map, self.orders, defensive_buffs=self.treaty_engine.defensive_buffs, topology=self.topology
        )
        self.map = new_map
        self.recent_events = [b["message"] for b in breach_events] + espionage_events + events
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
        self.time_remaining = 30
        self.run_bot_diplomacy()

    def _topology_to_dict(self) -> Dict[str, Any]:
        return {
            "territories": self.topology.territories,
            "adjacency": {t: sorted(n) for t, n in self.topology.adjacency.items()},
            "supply_centers": sorted(self.topology.supply_centers),
            "starting_positions": self.topology.starting_positions,
            "coordinates": self.topology.coordinates,
        }

    @staticmethod
    def _topology_from_dict(data: Dict[str, Any]) -> MapTopology:
        return MapTopology(
            territories=data["territories"],
            adjacency={t: set(n) for t, n in data["adjacency"].items()},
            supply_centers=set(data["supply_centers"]),
            starting_positions=data["starting_positions"],
            coordinates=data.get("coordinates", {}),
        )

    def to_state(self) -> Dict[str, Any]:
        """Serializes this session to a JSON-safe dict for persistence."""
        return {
            "map_mode": self.map_mode,
            "topology": self._topology_to_dict(),
            "turn": self.turn,
            "phase": self.phase.value,
            "time_remaining": self.time_remaining,
            "winner": self.winner,
            "messages": [m.model_dump() for m in self.messages],
            "orders": {f: [o.model_dump() for o in orders] for f, orders in self.orders.items()},
            "recent_events": self.recent_events,
            "bot_factions": self.bot_factions,
            "caster_script": self.caster_script,
            "treaty_engine": self.treaty_engine.to_dict(),
            "intel_reports": self.intel_reports,
            "map": {terr: ts.model_dump() for terr, ts in self.map.items()},
        }

    def restore(self, state: Dict[str, Any]) -> None:
        """Overwrites this session's state from a dict produced by to_state()."""
        self.map_mode = state.get("map_mode", "fixed")
        self.topology = (
            self._topology_from_dict(state["topology"]) if "topology" in state else CLASSIC_TOPOLOGY
        )
        self.turn = state["turn"]
        self.phase = Phase(state["phase"])
        self.time_remaining = state["time_remaining"]
        self.winner = state.get("winner")
        self.messages = [Message(**m) for m in state.get("messages", [])]
        self.orders = {f: [Order(**o) for o in orders] for f, orders in state.get("orders", {}).items()}
        self.bot_factions = state.get("bot_factions", {})
        self.treaty_engine = TreatyAndEspionageEngine.from_dict(state.get("treaty_engine", {}))
        self.intel_reports = state.get("intel_reports", [])
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

mmr_engine = BayesianMMREngine()

async def rate_finished_game(game: GameSession) -> None:
    """Updates and persists real agents' TrueSkill ratings when a genuine
    4-real-agent match finishes. Practice matches (bot_factions non-empty)
    are never rated - archetype bots have no AgentRecord, and this
    mirrors how app/gauntlet_runner.py's own bot-vs-candidate calibration
    battles already never touch agents_db (fresh, throwaway registry per
    call - bot opponents were never meant to affect the real leaderboard).
    """
    if game.bot_factions:
        return

    faction_to_agent = {
        m["faction"]: agent_id
        for agent_id, m in server_hub.assigned_matches.items()
        if m["game_id"] == game.game_id
    }
    if len(faction_to_agent) != 4:
        # Covers e.g. a game created directly via POST /api/v1/games
        # (admin/testing - no agents ever matched into it) reaching
        # FINISHED with nobody to rate. Skip rather than guess.
        return

    scores = game.calculate_scores()
    # Same convention app/gauntlet_runner.py already uses: a strict
    # placement_rank 1..4 from stable sort, even when SC counts tie.
    # BayesianMMREngine has no representation for a tied placement (its
    # adjacent-pairwise algorithm always treats index i as strictly
    # beating index i+1) - a real, pre-existing limitation of the shared
    # engine, not something this hook works around. A tie in
    # game.winner (e.g. "Red/Blue") is fully honored below for `wins`/
    # win-rate, but NOT reflected as a tie in the mu/sigma adjustment
    # itself - the tied factions still get distinct (arbitrary-among-
    # equals) placements for rating purposes.
    ranked = sorted(FACTIONS, key=lambda f: scores.get(f, 0), reverse=True)
    winners = set((game.winner or "").split("/"))

    registry: Dict[str, TrueSkillProfile] = {}
    records: Dict[str, server_hub.AgentRecord] = {}
    for faction in FACTIONS:
        agent_id = faction_to_agent[faction]
        api_key = server_hub.agent_id_lookup[agent_id]
        record = server_hub.agents_db[api_key]
        records[faction] = record
        registry[agent_id] = TrueSkillProfile(
            agent_id=agent_id,
            mu=record.mu,
            sigma=record.sigma,
            matches_played=record.matches_played,
            conservative_mmr=record.conservative_mmr,
        )

    snapshots = [
        MatchResultSnapshot(
            agent_id=faction_to_agent[faction],
            placement_rank=ranked.index(faction) + 1,
            final_sc=scores.get(faction, 0),
            # No real per-match persuasion/betrayal/deception scoring is
            # derived from live gameplay yet (see TODO.md) - neutral
            # constants collapse BayesianMMREngine's bench-modulator
            # multiplier to exactly 1.0, i.e. pure TrueSkill.
            persuasion_index=0.5,
            betrayal_efficiency=1.0,
            deception_resilience=0.5,
        )
        for faction in FACTIONS
    ]

    mmr_engine.update_match_ratings(snapshots, registry)

    for faction in FACTIONS:
        agent_id = faction_to_agent[faction]
        profile = registry[agent_id]
        record = records[faction]
        record.mu = profile.mu
        record.sigma = profile.sigma
        record.conservative_mmr = profile.conservative_mmr
        record.matches_played = profile.matches_played
        if faction in winners:
            record.wins += 1
        await save_agent_state(agent_id, record.model_dump())

async def release_finished_match_agents(game_id: str) -> None:
    """Frees every agent matched into this now-FINISHED game so their next
    POST /api/v1/queue/join actually queues them for a new match, instead of
    join_queue() finding their stale assigned_matches entry and handing back
    the same finished game_id/faction forever (the bug behind agents never
    accumulating more than one match on the leaderboard)."""
    stale_agent_ids = [
        agent_id
        for agent_id, m in server_hub.assigned_matches.items()
        if m["game_id"] == game_id
    ]
    for agent_id in stale_agent_ids:
        del server_hub.assigned_matches[agent_id]
        await delete_assigned_match(agent_id)

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
                if game.phase == Phase.FINISHED:
                    await rate_finished_game(game)
                    await release_finished_match_agents(game_id)
            await save_game_state(game_id, game.to_state())

async def spawn_game(
    game_id: str, topology: MapTopology = CLASSIC_TOPOLOGY, map_mode: str = "fixed"
) -> GameSession:
    """Creates and persists a new GameSession, and starts its game_loop task.
    Shared by the direct create-game endpoint and the matchmaker callback."""
    game = GameSession(game_id, topology=topology, map_mode=map_mode)
    games[game_id] = game
    await save_game_state(game_id, game.to_state())
    asyncio.create_task(game_loop(game_id))
    return game

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    for agent_id, state in (await load_all_agent_states()).items():
        record = server_hub.AgentRecord(**state)
        server_hub.agents_db[record.api_key] = record
        server_hub.agent_id_lookup[agent_id] = record.api_key
    for agent_id, state in (await load_all_assigned_matches()).items():
        server_hub.assigned_matches[agent_id] = state
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
async def create_game(map_mode: Literal["fixed", "generated"] = "fixed"):
    game_id = f"game_{len(games) + 1001}"
    topology = build_generated_topology() if map_mode == "generated" else CLASSIC_TOPOLOGY
    await spawn_game(game_id, topology=topology, map_mode=map_mode)
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
                "map_mode": g.map_mode,
            }
            for g in games.values()
        ]
    }

@app.get("/api/v1/leaderboard")
def get_leaderboard():
    """Public, no auth (same convention as GET .../games): every
    registered agent's real TrueSkill-derived rating, sorted by
    conservative_mmr descending. Populated by rate_finished_game() -
    only real 4-agent matches update it, never practice matches."""
    rows = []
    for record in server_hub.agents_db.values():
        win_rate = (record.wins / record.matches_played * 100) if record.matches_played else 0.0
        rows.append({
            "agent_name": record.agent_name,
            "developer_handle": record.developer_handle,
            "model_identifier": record.model_identifier,
            "matches_played": record.matches_played,
            "wins": record.wins,
            "win_rate": round(win_rate, 1),
            "conservative_mmr": record.conservative_mmr,
        })
    rows.sort(key=lambda r: r["conservative_mmr"], reverse=True)
    return {"leaderboard": rows}

@app.post("/api/v1/practice")
async def start_practice_match(
    map_mode: Literal["fixed", "generated"] = "fixed",
    agent: server_hub.AgentRecord = Depends(server_hub.authenticate_agent),
):
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

    topology = build_generated_topology() if map_mode == "generated" else CLASSIC_TOPOLOGY
    game = await spawn_game(game_id, topology=topology, map_mode=map_mode)
    game.bot_factions = {f: random.choice(list(ARCHETYPE_CLASSES.keys())) for f in bot_faction_names}
    game.run_bot_diplomacy()
    await save_game_state(game_id, game.to_state())

    server_hub.assigned_matches[agent.agent_id] = {
        "game_id": game_id,
        "faction": human_faction,
        "timestamp": time.time(),
    }
    await save_assigned_match(agent.agent_id, server_hub.assigned_matches[agent.agent_id])
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
        map_mode=game.map_mode,
        adjacency={t: sorted(n) for t, n in game.topology.adjacency.items()},
        supply_centers=sorted(game.topology.supply_centers),
        coordinates=game.topology.coordinates,
        submitted_orders={f: [o.model_dump() for o in orders] for f, orders in game.orders.items()},
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

@app.get("/api/v1/games/{game_id}/public-messages")
def read_public_messages(game_id: str, since_turn: int = 1):
    """Spectator-facing endpoint: returns only PUBLIC messages, no auth needed."""
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    public_messages = [
        m for m in game.messages
        if m.turn >= since_turn and m.recipient == "PUBLIC"
    ]
    return {"messages": public_messages}

@app.post("/api/v1/games/{game_id}/orders")
async def submit_orders(game_id: str, payload: Dict[str, Any], agent_faction: str = Depends(get_authorized_faction)):
    from .db import get_agent_season_hash, log_compliance_check, get_active_season

    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.phase != Phase.ORDERS:
        raise HTTPException(status_code=400, detail="Orders only accepted during ORDERS phase")

    # Verify prompt hash if provided (season compliance)
    compliance = payload.get("_compliance", {})
    if compliance:
        prompt_hash = compliance.get("prompt_hash")
        agent_id = compliance.get("agent_id")

        if prompt_hash and agent_id:
            season_id = await get_active_season()
            if season_id:
                registered_hash = await get_agent_season_hash(agent_id, season_id)
                verified = (registered_hash and prompt_hash == registered_hash)
                await log_compliance_check(
                    game_id=game_id,
                    turn=game.turn,
                    agent_id=agent_id,
                    prompt_hash=prompt_hash,
                    verified=verified,
                )
                if not verified:
                    raise HTTPException(
                        status_code=403,
                        detail="Prompt hash verification failed - your registered prompt does not match your runtime prompt"
                    )

    orders = payload.get("orders", [])
    game.orders[agent_faction] = orders
    await save_game_state(game_id, game.to_state())
    return {"status": "ACCEPTED", "turn": game.turn, "order_count": len(orders)}

def _treaty_to_dict(t) -> Dict[str, Any]:
    return {
        "treaty_id": t.treaty_id,
        "initiator": t.initiator,
        "signatory": t.signatory,
        "treaty_type": t.treaty_type.value,
        "target_territories": t.target_territories,
        "start_turn": t.start_turn,
        "duration_turns": t.duration_turns,
        "status": t.status.value,
        "breached_by": t.breached_by,
    }

@app.post("/api/v1/games/{game_id}/treaties", status_code=201)
async def propose_treaty(game_id: str, proposal: TreatyProposal, agent_faction: str = Depends(get_authorized_faction)):
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.phase != Phase.DIPLOMACY:
        raise HTTPException(status_code=400, detail="Treaties can only be proposed during DIPLOMACY phase")
    if proposal.signatory not in FACTIONS:
        raise HTTPException(status_code=422, detail=f"signatory must be one of {FACTIONS}")
    if proposal.signatory == agent_faction:
        raise HTTPException(status_code=422, detail="Cannot propose a treaty with yourself")
    try:
        treaty_type = TreatyType(proposal.treaty_type)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"treaty_type must be one of {[t.value for t in TreatyType]}")
    invalid_terrs = [t for t in proposal.target_territories if t not in game.topology.adjacency]
    if invalid_terrs:
        raise HTTPException(status_code=422, detail=f"Unknown territories: {invalid_terrs}")
    if proposal.duration_turns < 1:
        raise HTTPException(status_code=422, detail="duration_turns must be at least 1")

    treaty = game.treaty_engine.propose_treaty(
        initiator=agent_faction,
        signatory=proposal.signatory,
        treaty_type=treaty_type,
        territories=proposal.target_territories,
        current_turn=game.turn,
        duration=proposal.duration_turns,
    )
    await save_game_state(game_id, game.to_state())
    return _treaty_to_dict(treaty)

@app.post("/api/v1/games/{game_id}/treaties/{treaty_id}/sign")
async def sign_treaty(game_id: str, treaty_id: str, agent_faction: str = Depends(get_authorized_faction)):
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.phase != Phase.DIPLOMACY:
        raise HTTPException(status_code=400, detail="Treaties can only be signed during DIPLOMACY phase")
    signed = game.treaty_engine.sign_treaty(treaty_id, agent_faction)
    if not signed:
        raise HTTPException(status_code=400, detail="Treaty not found, already signed, or you are not its signatory")
    await save_game_state(game_id, game.to_state())
    return _treaty_to_dict(game.treaty_engine.active_treaties[treaty_id])

@app.get("/api/v1/games/{game_id}/intel")
def read_intel(game_id: str, agent_faction: str = Depends(get_authorized_faction)):
    """Intel packets from this agent's own resolved SPY orders (see
    app/treaties_engine.py::resolve_espionage_orders) - never exposed via
    the public GET .../state, since the whole point is that it's secret."""
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    visible = [r for r in game.intel_reports if r["spying_faction"] == agent_faction]
    return {"intel": visible}

@app.get("/api/v1/games/{game_id}/treaties")
def list_treaties(game_id: str, agent_faction: str = Depends(get_authorized_faction)):
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    visible = [
        _treaty_to_dict(t)
        for t in game.treaty_engine.active_treaties.values()
        if agent_faction in (t.initiator, t.signatory)
    ]
    return {"treaties": visible}

@app.get("/api/v1/games/{game_id}/public-treaties")
def read_public_treaties(game_id: str):
    """Spectator-facing endpoint: every treaty regardless of party, terms
    included, no auth needed (mirrors read_public_messages)."""
    game = games.get(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"treaties": [_treaty_to_dict(t) for t in game.treaty_engine.active_treaties.values()]}

# Mounted last so it only catches paths none of the /api/v1/... routes above
# matched - e.g. GET /spectator.html or / (index.html). Root-mounted (not
# under /static) to match streamer.sh's hardcoded
# http://localhost:8000/spectator.html and player.html's root-relative
# API_BASE fetches.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
