"""
Micro-Diplomacy Persistence Layer

Each GameSession is stored as a single JSON document keyed by game_id,
rather than a fully normalized relational schema - the game state (map,
messages, orders) is small, short-lived (games finish within 10 turns),
and already modeled as nested pydantic objects in app/main.py, so a
document-per-game store is the simplest thing that actually survives a
restart without a bigger relational-modeling effort.

Defaults to a local SQLite file (via aiosqlite) rather than Postgres to
match the project's target deployment: a single low-resource process on a
4GB-RAM Mac Mini (see PROJECT_HANDOFF.md), not a separate DB server.
Override with the DATABASE_URL env var for a different SQLAlchemy-async
backend if needed.
"""
import os
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import JSON, DateTime, String, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./diplomacy.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class GameRecord(Base):
    __tablename__ = "games"

    game_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[Dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class AgentRow(Base):
    """One row per registered agent (see app/server_hub.py's AgentRecord)
    - keyed by agent_id, not api_key, since agent_id is what a finished
    game's assigned_matches scan needs to look agents up by."""
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[Dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class AssignedMatchRow(Base):
    """One row per agent's current match assignment (see
    app/server_hub.py's assigned_matches) - without this surviving a
    restart, get_authorized_faction() 403s every real agent out of its
    own already-resumed game."""
    __tablename__ = "assigned_matches"

    agent_id: Mapped[str] = mapped_column(String, primary_key=True)
    state: Mapped[Dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def save_game_state(game_id: str, state: Dict[str, Any]) -> None:
    async with async_session() as session:
        record = await session.get(GameRecord, game_id)
        now = datetime.now(timezone.utc)
        if record:
            record.state = state
            record.updated_at = now
        else:
            session.add(GameRecord(game_id=game_id, state=state, updated_at=now))
        await session.commit()


async def load_all_game_states() -> Dict[str, Dict[str, Any]]:
    async with async_session() as session:
        result = await session.execute(select(GameRecord))
        return {row.game_id: row.state for row in result.scalars().all()}


async def save_agent_state(agent_id: str, state: Dict[str, Any]) -> None:
    async with async_session() as session:
        record = await session.get(AgentRow, agent_id)
        now = datetime.now(timezone.utc)
        if record:
            record.state = state
            record.updated_at = now
        else:
            session.add(AgentRow(agent_id=agent_id, state=state, updated_at=now))
        await session.commit()


async def load_all_agent_states() -> Dict[str, Dict[str, Any]]:
    async with async_session() as session:
        result = await session.execute(select(AgentRow))
        return {row.agent_id: row.state for row in result.scalars().all()}


async def save_assigned_match(agent_id: str, state: Dict[str, Any]) -> None:
    async with async_session() as session:
        record = await session.get(AssignedMatchRow, agent_id)
        now = datetime.now(timezone.utc)
        if record:
            record.state = state
            record.updated_at = now
        else:
            session.add(AssignedMatchRow(agent_id=agent_id, state=state, updated_at=now))
        await session.commit()


async def load_all_assigned_matches() -> Dict[str, Dict[str, Any]]:
    async with async_session() as session:
        result = await session.execute(select(AssignedMatchRow))
        return {row.agent_id: row.state for row in result.scalars().all()}
