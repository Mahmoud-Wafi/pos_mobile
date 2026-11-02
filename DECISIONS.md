# DECISIONS.md

Architectural and business-rule decisions made during development.

## Phase 1

### D-001 — Safety copy path for restore
**Decision**: The `restore_backup()` function saves a safety copy of the current DB in the same directory as `DB_PATH` (not in `BACKUP_DIR`), named `shop_safety_<timestamp>.db`.  
**Reason**: Safest option — keeps the last known good copy separate from the backup archive, preventing circular overwrites.

### D-002 — Alembic for production; `init_db()` for tests
**Decision**: Production uses `alembic upgrade head`; tests call `init_db(engine)` directly with an in-memory SQLite engine.  
**Reason**: Keeps tests fast, isolated, and independent of the migrations history, while production always goes through the migration path.

### D-003 — `python3.10` as the interpreter
**Decision**: All commands use `python3.10` because the packages (SQLAlchemy, Alembic, pytest) were installed with `pip3 install --user` which targets the `python3.10` user site-packages (`~/.local/lib/python3.10/`).  
**Impact**: `requirements.txt` pins compatible versions; `python3` symlink on this Ubuntu system points to 3.10 as well for the user path.

### D-004 — Default manager credentials
**Decision**: Seeded manager account: username=`admin`, password=`admin123`.  
**Reason**: Development convenience only. Production deployments must change this on first login (enforced by a future Settings screen prompt).

### D-005 — `PermissionDenied` raised in services, not silently swallowed
**Decision**: Any service call that violates RBAC raises `PermissionDenied` immediately, even if the UI has hidden the button.  
**Reason**: AGENTS.md §2 rule 5 explicitly requires this.
