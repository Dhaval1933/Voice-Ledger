"""
Database engine, session factory, and FastAPI dependency.
Uses SQLAlchemy 2.x with sync engine (compatible with both SQLite and PostgreSQL).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from typing import Generator

from backend.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""
    pass


def get_engine():
    """Create SQLAlchemy engine from settings."""
    settings = get_settings()
    connect_args = {}
    if settings.DATABASE_URL.startswith("sqlite"):
        # SQLite needs check_same_thread=False for FastAPI's threaded model
        connect_args = {"check_same_thread": False}
    return create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        echo=False,
    )


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db():
    """Create all database tables. Safe to call multiple times."""
    from backend import models  # noqa: F401 — import to register models
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
