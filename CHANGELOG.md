# Changelog

## Unreleased (branch `fix/dialogs-fit-screen`)
- Fixed: dialogs taller than the screen hid their save/cancel buttons; all dialogs now fit the screen with scrolling content and a pinned button bar (D-024).

## Unreleased (branch `fix/audit-round2`)
- Fixed: used-device purchase could overdraw the drawer and caused a false shift shortage.
- Fixed: one IMEI validation rule for add / edit / purchase invoice / used purchase.
- Fixed: unknown payment or refund methods are refused; void/return of a wallet-paid sale no longer pays cash from the drawer.
- Fixed: `sale.remaining` is updated when returns cancel debt.
- Fixed: Windows/PyInstaller build crashed at start-up (missing `logging.config`); build script completed.
- Tests: whole-cycle reconciliation, old-database backup/restore/upgrade (474 tests).

## Unreleased (branch `fix/audit-sales-integrity`)
- Fixed: duplicate product lines could oversell stock; concurrent sales are guarded by a write lock (D-022).
- Fixed: cash change was recorded as drawer income; the drawer now gets the net cash, receipts show tendered/change.
- Fixed: returns accepted zero/negative quantities and empty lists, and applied changes before validating; debt vs cash refund logic.
- Fixed: profit ignored returns; one net-of-returns definition now feeds all reports.
- Fixed: shift expected cash (drawer only, transfers, supplier payments); shift shortage/overage now reconciles the drawer.
- Fixed: supplier payments could drive an account negative or exceed what is owed.
- Service-level permission checks on sale lines; IMEI format checks in services.
- New migration d5f1b3c7a901 (sales.cash_tendered, sales.change_given). 452 tests.

## Unreleased (branch `feat/machine-license`)
- Per-computer licence: activation screen with machine code; owner issues an activation code with `tools/make_license.py` (D-021).

## Unreleased (branch `feat/auto-barcode`)
- New product form (also from a purchase invoice) pre-fills the barcode with a random unused EAN-13 (prefix 2); it can still be replaced by scanning or typing.

## Unreleased (branch `feat/ui-polish-suppliers-hardware`)
- Supplier ledger: click a supplier to see every invoice and every payment; payments can be tied to an invoice. See D-020.
- Wallets: commission rules can be edited and deleted by the manager.
- Fixed: phone-model field did not accept typing (add device, used device); repair delivery failing for non-"ready" tickets.
- New: separate hardware settings (receipt printer, label printer and size, barcode-reader test).
- UI: reports/profit, backup screen, customers/debts action buttons, Arabic cash-ledger categories.

## Unreleased (branch `fix/numeric-fields-and-new-product`)
- Fixed: money/number fields could not be typed with a decimal point on Arabic-locale Windows (wallets, expenses, products, ... all "did nothing"). See D-019.
- Fixed: adding a customer always failed (wrong service call); collecting a customer payment always failed (wrong argument name) and now credits the chosen cash account.
- New: "+ منتج جديد" inside the purchase invoice; the new product is selected automatically and its stock is added by the invoice only.
- Wallet screen hides "new wallet" and "commission rules" for roles without `wallet.manage`.
- Tests: typed-input tests under English and Arabic (Egypt) locales for every money dialog, a static UI-to-service signature check, and MainWindow wallet flow (388 tests).

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
