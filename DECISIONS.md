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

## Phase 2 — Inventory

### D-006 — Dual IMEI uniqueness checking
**Decision**: Uniqueness is strictly enforced across both `imei1` and `imei2`. An IMEI cannot exist as `imei1` or `imei2` on any device in the database.
**Reason**: Prevents duplicate registration of dual-SIM devices or cross-referencing conflicts.

### D-007 — Stock integrity for IMEI items vs Non-IMEI items
**Decision**: For non-IMEI items, `stock.quantity` is driven by and equals the sum of `stock_movements.quantity`. For IMEI items, `stock.quantity` mirrors the live count of devices with `status='in_stock'`.
**Reason**: Aligns with AGENTS.md §5: "for non-IMEI items; for IMEI items quantity = count of devices in_stock".

### D-008 — Excel Import Format
**Decision**: The importer accepts both Arabic and English header names (e.g. `الاسم`/`name`, `الباركود`/`barcode`, `الكمية`/`quantity`) and converts Egyptian Pound amounts to integer piasters using `egp_to_piasters`.
**Reason**: Maximum user convenience when importing vendor price lists or existing shop sheets.


## Phase 0/1 — Foundations & security

### D-009 — Time: store naive UTC, think in Africa/Cairo
**Decision**: The DB keeps naive UTC datetimes. `app/core/clock.py` is the only place that converts; days, daily close, reports, wallet quotas, invoice numbers and printed times use the shop's local day (`day_bounds_utc`, `local_today`, `fmt_local`). Override the zone with `POS_TIMEZONE`.
**Reason**: sales between 00:00 and 02:00/03:00 Cairo time were previously counted in the previous day.

### D-010 — Data in a per-user folder; Alembic runs at start-up
**Decision**: `DATA_DIR` defaults to `%APPDATA%/MobileShopPOS` (Windows) / `~/.local/share/MobileShopPOS`; `POS_DATA_DIR` overrides. `startup.run_migrations()` upgrades to head (legacy `create_all` databases are stamped). Logs go to `DATA_DIR/logs/app.log`.
**Reason**: the packaged app cannot write beside its own files and users must not run Alembic by hand.

### D-011 — Login, idle lock and first-login password change
**Decision**: `SessionController` owns login -> main window -> logout/lock. Idle timeout comes from the `idle_lock_minutes` setting (0 disables). Accounts still using a seeded default password must change it before continuing (detected by verifying the known defaults, no schema change).

### D-012 — UI permission map is a hint, services still enforce
**Decision**: `app/ui/access.py` decides which screens are shown per permission set; views a user cannot open are not even constructed.
