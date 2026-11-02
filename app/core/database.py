"""SQLAlchemy engine, session factory, and base model for the shop system."""
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    """Enable WAL mode and foreign keys for every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def build_engine(url: str = DATABASE_URL):
    engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


# Module-level singletons (replaced in tests via dependency injection)
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal


def get_session() -> Session:
    """Return a new session from the factory (caller must close it)."""
    return get_session_factory()()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine=None):
    """Create all tables (used in tests; production uses Alembic)."""
    if engine is None:
        engine = get_engine()
    Base.metadata.create_all(engine)


def override_engine(engine):
    """Replace the module-level engine and session factory (for testing)."""
    global _engine, _SessionLocal
    _engine = engine
    _SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

