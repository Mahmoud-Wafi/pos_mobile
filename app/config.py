"""Application configuration."""
from pathlib import Path
import os

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Data directory (user data, backups, DB)
DATA_DIR = Path(os.environ.get("POS_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Database
DB_PATH = DATA_DIR / "shop.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Backups
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Alembic migrations directory
MIGRATIONS_DIR = BASE_DIR / "migrations"

# Security
MAX_FAILED_ATTEMPTS = 5          # lock account after this many failures
LOCKOUT_MINUTES = 15             # how long account stays locked
IDLE_LOCK_MINUTES_DEFAULT = 10   # default idle-lock timeout (overridable via Settings)

# Application
APP_NAME = "نظام إدارة محل الموبايلات"
APP_VERSION = "1.0.0"

