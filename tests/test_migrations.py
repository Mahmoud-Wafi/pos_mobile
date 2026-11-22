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


def test_upgrade_from_previous_revision_and_back(tmp_path, monkeypatch):
    """The sale-change migration upgrades an existing database (defaults 0) and can be rolled back."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    from app.config import BASE_DIR
    url = f"sqlite:///{tmp_path / 'step.db'}"
    monkeypatch.setattr(startup, "DATABASE_URL", url)
    monkeypatch.setattr("app.config.DATABASE_URL", url)
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    engine = create_engine(url)
    command.upgrade(cfg, "c4e8a2d90f33")
    assert "change_given" not in {c["name"] for c in inspect(engine).get_columns("sales")}
    command.upgrade(cfg, "head")
    cols = {c["name"]: c for c in inspect(engine).get_columns("sales")}
    assert "change_given" in cols and "cash_tendered" in cols
    command.downgrade(cfg, "c4e8a2d90f33")
    assert "change_given" not in {c["name"] for c in inspect(engine).get_columns("sales")}
    command.upgrade(cfg, "head")


def _insert_row(con, table, **given):
    """Insert a row filling every other NOT NULL column with a neutral value (works on any older schema)."""
    cols = con.execute(f"PRAGMA table_info({table})").fetchall()      # cid, name, type, notnull, default, pk
    values = {}
    for _cid, name, typ, notnull, default, pk in cols:
        if name in given:
            values[name] = given[name]
        elif notnull and default is None and not pk:
            t = (typ or "").upper()
            values[name] = 0 if "INT" in t or "BOOL" in t else ("2026-01-01 00:00:00" if "DATE" in t else "x")
    con.execute(f"INSERT INTO {table} ({','.join(values)}) VALUES ({','.join('?' * len(values))})",
                list(values.values()))


def test_old_database_with_real_data_survives_backup_restore_and_upgrade(tmp_path, monkeypatch):
    """A database from the previous release (with a sale in it) -> backup -> restore elsewhere -> upgrade to head."""
    import sqlite3
    from alembic import command
    from alembic.config import Config
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.config import BASE_DIR
    from app.core import backup as core_backup

    old_db = tmp_path / "old" / "shop.db"
    old_db.parent.mkdir()
    url = f"sqlite:///{old_db}"
    monkeypatch.setattr(startup, "DATABASE_URL", url)
    monkeypatch.setattr("app.config.DATABASE_URL", url)
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "c4e8a2d90f33")                                      # the previous release's schema

    con = sqlite3.connect(old_db)
    _insert_row(con, "users", id=1, username="boss", full_name="Boss")
    _insert_row(con, "customers", id=1, name="Ali")
    _insert_row(con, "sales", id=1, invoice_no="INV-OLD-1", customer_id=1, user_id=1, subtotal=100000,
                discount=0, total=100000, paid=40000, remaining=60000, status="posted")
    con.commit()
    con.close()

    # backup the old database, then restore it into a brand-new location (as after a disk failure)
    backups = tmp_path / "backups"
    zipped = core_backup.create_backup(old_db, backups)
    info = core_backup.verify_backup(zipped)
    assert info                                                               # verified, not just "a file exists"
    new_db = tmp_path / "new" / "shop.db"
    core_backup.restore_backup(zipped, new_db, tmp_path / "new_backups")

    # the restored copy is still the OLD schema; the new app upgrades it in place and keeps every number
    new_url = f"sqlite:///{new_db}"
    monkeypatch.setattr(startup, "DATABASE_URL", new_url)
    monkeypatch.setattr("app.config.DATABASE_URL", new_url)
    engine = create_engine(new_url)
    startup.run_migrations(engine)

    con = sqlite3.connect(new_db)
    row = con.execute("SELECT invoice_no, total, paid, remaining, cash_tendered, change_given FROM sales").fetchone()
    assert row == ("INV-OLD-1", 100000, 40000, 60000, 0, 0)
    assert con.execute("SELECT count(*) FROM customers").fetchone()[0] == 1
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "d5f1b3c7a901"
    con.close()

    import app.models  # noqa: F401
    with engine.connect() as c:
        assert compare_metadata(MigrationContext.configure(c), Base.metadata) == []
    engine.dispose()
