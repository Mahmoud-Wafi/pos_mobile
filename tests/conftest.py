"""Shared pytest fixtures for all tests."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, override_engine
from app.core.seed import seed_database


@pytest.fixture
def db_engine():
    """In-memory SQLite engine with WAL pragma and FK enabled."""
    from sqlalchemy import event

    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    def _pragmas(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    event.listen(engine, "connect", _pragmas)
    Base.metadata.create_all(engine)
    # Point the module-level singletons at this engine
    override_engine(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Session seeded with roles + default settings + admin user."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    seed_database(session)
    yield session
    session.close()
