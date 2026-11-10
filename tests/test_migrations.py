"""Migrations must produce exactly the schema the models describe."""
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.core import startup
from app.core.database import Base


def test_alembic_head_matches_models(tmp_path, monkeypatch):
    db = tmp_path / "mig.db"
    url = f"sqlite:///{db}"
    monkeypatch.setattr(startup, "DATABASE_URL", url)
    monkeypatch.setattr("app.config.DATABASE_URL", url)
    engine = create_engine(url)
    startup.run_migrations(engine)

    import app.models  # noqa: F401  (register every model)

    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], f"models and migrations drifted: {diff}"


def test_legacy_database_is_stamped_not_recreated(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    monkeypatch.setattr(startup, "DATABASE_URL", url)
    monkeypatch.setattr("app.config.DATABASE_URL", url)
    engine = create_engine(url)
    import app.models  # noqa: F401
    Base.metadata.create_all(engine)          # legacy: tables, no alembic_version
    startup.run_migrations(engine)            # must not raise "table already exists"
    from sqlalchemy import inspect
    assert "alembic_version" in inspect(engine).get_table_names()
