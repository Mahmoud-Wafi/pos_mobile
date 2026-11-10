"""Application configuration."""
from pathlib import Path

from app.core.paths import default_data_dir, resource_dir

# Folder with bundled read-only resources (assets, migrations)
BASE_DIR = resource_dir()

# Data directory (user data, backups, DB, logs). Per-user folder; override with POS_DATA_DIR.
DATA_DIR = default_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = DATA_DIR / "logs"
DECLARATIONS_DIR = DATA_DIR / "declarations"

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

