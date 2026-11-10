"""Application start-up helpers: logging, migrations, global error handling."""
from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler

from sqlalchemy import inspect

from app.config import BASE_DIR, DATABASE_URL, LOG_DIR

log = logging.getLogger("pos")


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)


def run_migrations(engine=None) -> None:
    """Bring the database to the latest Alembic revision (creating it if new).

    A legacy database created through ``create_all`` (tables but no
    ``alembic_version``) is stamped at head instead of re-created.
    """
    from alembic import command
    from alembic.config import Config

    from app.core.database import get_engine

    engine = engine or get_engine()
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    tables = set(inspect(engine).get_table_names())
    if tables and "alembic_version" not in tables:
        log.warning("Database has tables but no alembic_version; stamping head")
        command.stamp(cfg, "head")
    else:
        command.upgrade(cfg, "head")
    log.info("Database is at the latest revision")


def install_excepthook(show_dialog=None) -> None:
    """Log every uncaught exception; optionally show a friendly dialog."""

    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Uncaught exception:\n%s", text)
        if show_dialog:
            try:
                show_dialog(text)
            except Exception:  # never let the handler itself crash the app
                log.exception("Error dialog failed")

    sys.excepthook = _hook
