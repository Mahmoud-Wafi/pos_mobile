# Acceptance criteria — all phases

Status legend: `[x]` done and verified (a test or a check was run) · `[ ]` not done yet · `[~]` partly done (see the note).
Baseline before this work: 114 tests. Current: 164 passing (`QT_QPA_PLATFORM=offscreen pytest -q`).

**Global gate for every phase**
- [ ] `QT_QPA_PLATFORM=offscreen pytest -q` is fully green, with no skipped or deleted tests.
- [ ] `alembic revision --autogenerate` finds no schema difference (covered by `tests/test_migrations.py`).
- [ ] One commit per phase, titled `phase N: <summary>`. New decisions are logged in `DECISIONS.md`.
- [ ] After Phases 2, 3 and 5: run the app and check screenshots of login, dashboard, POS, payment dialog, inventory, reports and settings for RTL alignment, contrast and clipped text.

---

## Phase 0 — Foundations

| # | Criterion | Status |
|---|---|---|
| 0.1 | `.venv/`, `__pycache__/`/`*.pyc` and `data/shop.db` are not tracked by git (`git ls-files` shows none). `data/.gitkeep` is kept. | [x] |
| 0.2 | A `LICENSE` file exists. | [ ] |
| 0.3 | The owner is told to rotate `admin123` and to decide whether to purge git history (the old DB is still in history). | [x] (said in the hand-off) |
| 0.4 | All timestamps are stored as naive UTC through `app/core/clock.py`. No `datetime.utcnow()` or `date.today()` outside it. | [x] |
| 0.5 | A sale made at 00:30 Cairo time is counted on that local day in sales report, daily close, dashboard and wallet daily quota, and not on the previous day. Winter (UTC+2) and summer (UTC+3) are both tested. | [x] |
| 0.6 | Receipts, reports and screens show local time, not UTC. | [x] (receipt, report rows, dashboard times) |
| 0.7 | No `float` or `/ 100` money formatting in `app/` (grep). Money parsing goes through `parse_egp_input` / `piasters_to_input` / `parse_percent_to_bp` (Decimal, accepts Arabic digits, rejects negative / NaN / empty). | [x] |
| 0.8 | A reusable `MoneyLineEdit` widget with a validator exists and is used by money fields. | [ ] |
| 0.9 | On a machine with no database, `python -m app.main` creates and migrates the DB by itself (no manual `alembic upgrade`). A legacy DB without `alembic_version` is stamped, not recreated. | [x] |
| 0.10 | Data lives in a per-user folder (`%APPDATA%/MobileShopPOS`, `~/.local/share/MobileShopPOS`); `POS_DATA_DIR` overrides it. Declaration PDFs are saved under it, not under a relative `data/`. | [x] |
| 0.11 | Rotating log file at `DATA_DIR/logs/app.log`. A global exception hook logs the traceback and shows a friendly Arabic dialog. | [x] |
| 0.12 | No silent `except Exception: pass` in the UI. Every caught error is logged or shown. | [ ] (the dashboard and about 50 other handlers still swallow errors) |
| 0.13 | README matches reality: clone URL, `python -m app.main`, bcrypt, auto-migration, data folder. | [~] (fixed; the PyInstaller section and feature claims are re-checked in Phase 5) |
| 0.14 | A packaging script or `.spec` builds an `.exe`, `assets/icon.ico` exists, and assets/migrations are found through one resource helper (works under `sys._MEIPASS`). | [~] (resource helper done; spec, icon and a real build are not) |

## Phase 1 — Security and access

| # | Criterion | Status |
|---|---|---|
| 1.1 | The main window cannot be reached without a valid login; there is no auto-login as `admin`. | [x] |
| 1.2 | Wrong credentials show an Arabic error. Five failed attempts lock the account, and the right password is still refused while locked. Inactive accounts are refused. | [x] |
| 1.3 | A user still on a seeded default password (`admin123`, `cashier123`, `wallet123`) must change it before reaching the app, and cannot dismiss that dialog. The new password is at least 6 characters and not a default. | [x] |
| 1.4 | The header has a user menu with change password, lock and logout. Logout and lock write audit entries and return to the login screen. | [x] |
| 1.5 | After `idle_lock_minutes` without input the session locks and the login screen returns. `0` disables the lock. | [~] (implemented with an event filter; there is no automated test of the timer itself) |
| 1.6 | Each role sees only its screens: wallet staff see Dashboard and Wallets only; cashiers see no Settings; managers see all 10. Views a user cannot open are not built. | [x] |
| 1.7 | Cost and profit values are hidden everywhere without `cost.view` / `profit.view`, including inventory cost columns and the dashboard profit card. | [ ] (reports and dashboard profit are guarded by the service; inventory columns and the card are not hidden in the UI) |
| 1.8 | `PermissionDenied` raised by a service is shown as a clear Arabic message everywhere, never as raw exception text. Buttons the role cannot use are disabled. | [ ] |
| 1.9 | Manager approval: a cashier going over the discount limit, below the minimum price, past the stock level or past a customer's credit limit gets an approval dialog. A valid manager login lets the action proceed and is audited as `manager_override`. A non-manager login or a wrong password is refused. A declined discount resets to zero. | [x] |
| 1.10 | User management (manager only): add, edit, change role, deactivate, reset password, unlock. A user cannot deactivate themselves, and the last active manager cannot be demoted or deactivated. Every change is audited. | [x] |
| 1.11 | Shop settings (name, address, phone, invoice footer, warranty text, cashier discount limit, idle minutes) are editable, validated and audited. Receipts and the used-device declaration read them. | [x] (thermal receipt and declaration; the A4 invoice joins in Phase 3) |
| 1.12 | Audit viewer: filter by date, user and action; CSV export that opens correctly in Arabic Excel. Only users with `audit.view` can open it. | [x] |

## Phase 2 — Design system

| # | Criterion | Status |
|---|---|---|
| 2.1 | `app/ui/design/tokens.py` defines colors (semantic names), spacing (4/8/12/16/24), radii (8/12) and a type scale (12/13/14/16/20/28). The global QSS is generated from the tokens. | [ ] |
| 2.2 | Component library in `app/ui/components/`: Card, KpiCard, PageHeader, button variants (primary / secondary / danger / ghost), StatusPill, DataTable, SearchField, MoneyLineEdit, FormRow, Toast, ConfirmDialog, EmptyState. | [ ] |
| 2.3 | At most about 15 inline `setStyleSheet` calls remain in `app/ui` (currently 291), and only for dynamic values. The sidebar active state is a QSS state, not an inline override. | [ ] |
| 2.4 | Emoji used as icons are replaced by a bundled SVG set (Lucide or Tabler, MIT, license file included), tinted by state, with text labels kept. | [ ] |
| 2.5 | App shell: header with shop name, shift pill and user menu; icon sidebar with the active mark on the right edge and `Ctrl+1…9` shortcuts; status bar with DB state, last backup, user and version. Window size and position are remembered. Works at 1366×768, 1920×1080 and 125%/150% scaling. | [ ] |
| 2.6 | Success messages are auto-dismissing toasts. Errors are short Arabic messages with an optional details section and never show Python exception text. Destructive actions use `ConfirmDialog`. | [ ] |
| 2.7 | Contrast meets WCAG AA (secondary text at least `#64748B` on white). Visible 2 px focus ring on buttons, inputs and tabs (the global `outline: none` is removed). Minimum control height 40 px, base font 13–14 px, never below 12 px. | [ ] |

## Phase 3 — Sales flow

| # | Criterion | Status |
|---|---|---|
| 3.1 | A shift can be closed from the UI with a **blind count**: the expected cash is not visible until the count is confirmed. Then expected, actual and difference (surplus or shortage) are shown and stored. Only the shift's owner or a manager can close it. | [x] |
| 3.2 | The sidebar shift card and the POS bar show the real shift state (open with id and time, or closed) and refresh on open and close. | [x] |
| 3.3 | A printable shift summary can be produced after closing. | [ ] |
| 3.4 | POS search: several matching products open a type-ahead list (name, price, stock) instead of silently taking the first. IMEI products with several in-stock units show a unit chooser (oldest first by default). | [ ] |
| 3.5 | Cart rows allow quantity change for non-IMEI lines, line discount and price override (permission-gated, with manager approval where required) and remove with undo. Held invoices open in a drawer with a count badge. | [ ] |
| 3.6 | A full sale can be completed with the keyboard only (scan → pay → confirm → focus returns to the scan field). The payment dialog has quick cash buttons, auto-filled remainder and a highlighted change due. | [ ] |
| 3.7 | Invoice history screen: filter by date, customer, cashier, status, invoice number and IMEI; details panel; reprint; return; **void** (manager only, reason required, audited). | [ ] |
| 3.8 | Arabic PDFs render correctly: Cairo font registered, text shaped and bidi-ordered. A test extracts the text of the A4 invoice and the used-device declaration and finds the Arabic. Shop name, address, phone, footer and warranty text come from settings. | [ ] |
| 3.9 | Real printing: 80 mm thermal receipt through a print dialog or preview (ESC/POS optional), and A4 warranty invoice opened as a PDF. Printer choice is stored in settings. Reprint works from invoice history. | [ ] |
| 3.10 | Print templates (UX-09): receipt with phone, address, local time, IMEI, totals, paid, change, remaining, footer and an optional invoice-number barcode; A4 invoice with per-item warranty; declaration with signature and thumbprint boxes. | [ ] |

## Phase 4 — Data and reports

| # | Criterion | Status |
|---|---|---|
| 4.1 | Backups use SQLite's online backup (not a file copy), are zipped with a manifest (app version, Alembic revision, time, sha256), and require `backup.manage`. | [ ] |
| 4.2 | Restore checks integrity and the manifest, rejects a tampered file, disposes the engine, removes stale `-wal` / `-shm` files and offers an automatic restart. A backup taken during an open write transaction restores cleanly (tested). | [ ] |
| 4.3 | Automatic backup on app close and daily, with retention N (a setting, default 14). The last backup time shows in the status bar. | [ ] |
| 4.4 | Excel import wizard (`.xlsx` / `.csv` → preview → per-row errors → confirm) using the Arabic/English headers from D-008, with a downloadable template. Real `.xlsx` export (RTL sheet) for inventory, devices and reports, next to CSV with BOM. | [ ] |
| 4.5 | The one shared SQLAlchemy session is replaced screen by screen with a session per user action (or at least rollback on error and `expire_all()` on view switch). A failed action in one screen never breaks another. Tests stay green after each screen. | [ ] |
| 4.6 | New dashboard: unified KPI cards with comparison to yesterday, 7-day sales chart, top 5 products, per-wallet balance strip (`QtCharts`, offline), reorder shortcut from the low-stock list, empty/loading states. The profit card is hidden without permission. | [ ] |
| 4.7 | Tables are consistent: right-aligned text, row height at least 40 px, sortable headers, remembered column widths, empty-state messages, icon row actions with tooltips. Western digits are shown everywhere; Arabic-Indic input is accepted. | [ ] |
| 4.8 | Forms validate inline (red border and helper text), tab order is sensible, `Enter` submits and `Esc` cancels. IMEI fields check Luhn on blur and show ✓/✗. Restore needs a typed confirmation. | [ ] |

## Phase 5 — Quality and release

| # | Criterion | Status |
|---|---|---|
| 5.1 | All user-facing Arabic text in `app/ui` and service error messages goes through `app/i18n/ar.py`. | [ ] (new code does; older UI and service strings do not) |
| 5.2 | UI smoke tests: login; `MainWindow` for each of the three roles; every view's refresh; the full POS flow (scan → pay → post → print panel); the close-shift flow. | [~] (login, role navigation, approval, discount, settings tabs, shift close exist; the full POS post flow and per-view refresh tests do not) |
| 5.3 | A Windows `.exe` is built from a committed spec, runs on a clean machine without Python, and creates its data in the per-user folder. | [ ] |
| 5.4 | README is rewritten to match what the repo really does (features, setup, build, roles, screenshots). A `CHANGELOG.md` is added. | [ ] |
| 5.5 | Definition of done: a full day works end to end (open shift → sell by cash, split and credit → return → void → close shift → daily close → backup → restore); the cashier sees no cost or profit; printed and PDF documents show correct Arabic, shop settings and local time; no float money, no `utcnow()`, no committed `.venv` / `.pyc` / `.db`. | [ ] |

---

## How to verify

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
QT_QPA_PLATFORM=offscreen pytest -q          # all green
grep -rn "/ 100\|float(" app --include=*.py  # only Decimal-based hits in core/money.py and the commission table
grep -rn "utcnow\|date.today" app --include=*.py   # only app/core/clock.py (and `from ... import utcnow`)
git ls-files | grep -E "\.venv|__pycache__|\.db$"  # empty
python -m app.main                            # login screen appears; admin / admin123 forces a password change
```

## Summary of progress

| Phase | Done | Partly | Open |
|---|---|---|---|
| 0 Foundations | 9 | 2 | 3 |
| 1 Security and access | 9 | 1 | 2 |
| 2 Design system | 0 | 0 | 7 |
| 3 Sales flow | 2 | 0 | 8 |
| 4 Data and reports | 0 | 0 | 8 |
| 5 Quality and release | 0 | 1 | 4 |
