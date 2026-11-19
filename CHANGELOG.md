# Changelog

## Unreleased (branch `fix-purchases-stock-reset`)
- New product form has "current quantity" (opening stock) so a new product no longer shows 0.
- Purchase invoices: product search box, Enter adds the line, hint when no supplier exists; the invoices list now opens a details view (products, quantities, costs, IMEIs) and shows local time.
- Products can have several barcodes; scanning any of them finds the product in POS, purchase invoices, search and the product form (which opens the existing product instead of creating a duplicate). Label codes (`P000123`) are scannable too.
- `scripts/reset_data.py`: wipe all data, leaving only `admin / admin123` and the built-in cash customer.

## Unreleased (branch `crud-inventory`)
- Edit / delete / deactivate products and edit / delete / write off devices, with history-aware rules (D-017); cashiers no longer see cost fields.

## Unreleased (branch `features-next`)

### Added
- Repairs: intake tickets, status flow, deposits/payments through the drawer, delivery, cancel with refund, customer message (WhatsApp link + copy), A5 receipt PDF; delivered-repair profit in the daily close.
- Warranty claims log (open / in repair / resolved / rejected) with a claims screen.
- Barcode labels (Code 128, 50x30 mm) for products and IMEIs.
- Off-site backup copy to a USB drive or synced folder, verified, with a status-bar indicator.
- End-to-end full-day test; app icon.

## Unreleased (branch `antigravity-improvements`)

### Added
- Design system (tokens, generated QSS, Lucide icons, shared components, toasts, confirm dialogs).
- Rebuilt app shell: header with shift pill, sidebar shortcuts (Ctrl+1..9), status bar, remembered window size.
- POS: editable cart with price/discount rules, held invoices, invoice history and search.
- Backups: online SQLite backup in a zip with manifest and checksum, verified restore with typed confirmation, daily/on-close auto-backup, retention.
- Excel/CSV import wizard with preview and per-row errors; real RTL `.xlsx` export.
- Dashboard: KPIs vs. yesterday, 7-day chart, top products, wallet strip, reorder shortcut.
- App-wide table defaults (row height, remembered column widths, numeric sorting in `DataTable`).
- IMEI fields validate Luhn on blur.
- PyInstaller spec and Windows build script in `packaging/`.

### Changed
- Shared DB session is rolled back and refreshed on every screen switch.
- Money is integer piasters everywhere except export-only cells.

See `DECISIONS.md` (D-001 … D-015) for the reasoning.
