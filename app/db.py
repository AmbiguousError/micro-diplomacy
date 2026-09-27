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
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, String, select, ForeignKey
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


class SeasonRow(Base):
    """Tournament season: tracks registration deadlines and prompt locking."""
    __tablename__ = "seasons"

    season_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # "draft", "active", "locked"
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    locked_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class AgentSeasonRow(Base):
    """Agent registration for a season: stores prompt hash at registration time."""
    __tablename__ = "agent_seasons"

    agent_id: Mapped[str] = mapped_column(String, primary_key=True)
    season_id: Mapped[str] = mapped_column(String, primary_key=True)
    prompt_name: Mapped[str] = mapped_column(String)  # e.g. "machiavelli"
    prompt_hash: Mapped[str] = mapped_column(String)  # sha256 of prompt text
    registered_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class ComplianceLogRow(Base):
    """Audit trail: logs every prompt hash verification attempt."""
    __tablename__ = "compliance_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String)
    turn: Mapped[int] = mapped_column(default=1)
    agent_id: Mapped[str] = mapped_column(String)
    prompt_hash: Mapped[str] = mapped_column(String)
    verified: Mapped[bool] = mapped_column(default=False)
    timestamp: Mapped[datetime] = mapped_column(
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


async def delete_assigned_match(agent_id: str) -> None:
    async with async_session() as session:
        record = await session.get(AssignedMatchRow, agent_id)
        if record:
            await session.delete(record)
            await session.commit()


# Season Management
async def create_season(season_id: str, name: str) -> None:
    async with async_session() as session:
        session.add(SeasonRow(season_id=season_id, name=name, status="active"))
        await session.commit()


async def lock_season(season_id: str) -> None:
    async with async_session() as session:
        record = await session.get(SeasonRow, season_id)
        if record:
            record.status = "locked"
            record.locked_at = datetime.now(timezone.utc)
            await session.commit()


async def get_active_season() -> str:
    """Returns the current active season_id."""
    async with async_session() as session:
        result = await session.execute(
            select(SeasonRow).where(SeasonRow.status == "active")
        )
        row = result.scalars().first()
        return row.season_id if row else None


# Agent-Season Registration
async def register_agent_for_season(agent_id: str, season_id: str, prompt_name: str, prompt_hash: str) -> None:
    async with async_session() as session:
        session.add(
            AgentSeasonRow(
                agent_id=agent_id,
                season_id=season_id,
                prompt_name=prompt_name,
                prompt_hash=prompt_hash,
            )
        )
        await session.commit()


async def get_agent_season_hash(agent_id: str, season_id: str) -> str:
    """Returns registered prompt hash for agent in season, or None."""
    async with async_session() as session:
        result = await session.execute(
            select(AgentSeasonRow).where(
                (AgentSeasonRow.agent_id == agent_id)
                & (AgentSeasonRow.season_id == season_id)
            )
        )
        row = result.scalars().first()
        return row.prompt_hash if row else None


# Compliance Logging
async def log_compliance_check(game_id: str, turn: int, agent_id: str, prompt_hash: str, verified: bool) -> None:
    async with async_session() as session:
        session.add(
            ComplianceLogRow(
                game_id=game_id,
                turn=turn,
                agent_id=agent_id,
                prompt_hash=prompt_hash,
                verified=verified,
            )
        )
        await session.commit()


async def get_first_ladder_prompt_hash(game_id: str, agent_id: str) -> Optional[str]:
    """Get the first prompt hash submitted by an agent in a ladder game.

    Ladder games don't have formal season registration, so we track the
    first-provided hash per agent/game and require consistency thereafter."""
    async with async_session() as session:
        result = await session.execute(
            select(ComplianceLogRow.prompt_hash)
            .where(
                (ComplianceLogRow.game_id == game_id) &
                (ComplianceLogRow.agent_id == agent_id)
            )
            .order_by(ComplianceLogRow.id.asc())
            .limit(1)
        )
        row = result.scalar()
        return row
