# Audit report — POS_Mobile (fixes of 2026-11-21)

Licensing was explicitly out of scope and was not touched.

## A. Bugs found and fixed
| # | Issue | Where | Severity | Root cause | Fix | Tests |
|---|---|---|---|---|---|---|
| 1 | Duplicate lines of one product oversell stock | `sales_service.post_sale`, `update_line` | Critical | stock checked per line, not per product | totals per product; write lock + re-read; duplicate IMEI line rejected | `TestAggregatedStock`, two-session test |
| 2 | Change booked as drawer income | `post_sale` | Critical | whole tendered cash added to drawer | net cash to drawer; `cash_tendered`/`change_given`; non-cash overpay rejected | `TestCashChange` |
| 3 | Invalid returns accepted; partial apply | `return_sale_items` | Critical | no validation before changes | validate-then-apply; zero/negative/empty/duplicate/excess rejected; exact proportional refund | `TestReturns` |
| 4 | Refund cancelled unrelated customer debt | `return_sale_items` | Major | used customer's whole balance | debt part limited to this sale's unpaid part | `test_return_against_credit_sale...`, `test_unrelated_debt...` |
| 5 | Void failed after a partial return | `void_sale` | Major | tried to return full quantities | returns only the remainder | `test_void_after_partial_return...` |
| 6 | Profit ignored returns | `report_service`, `accounting_service` | Critical | no return impact | `sales_profit.net_sales_profit` | `TestProfitAfterReturns` |
| 7 | Shift expected cash wrong | `shift_service.calculate_expected_cash` | Major | counted non-drawer accounts, ignored transfers, supplier payments had no shift | drawer-only, transfers, shift on supplier payments | `TestShiftLifecycle` |
| 8 | Shift difference never reached the drawer balance | `close_shift` | Major | only stored on the shift | `shift_diff` adjustment entry (not double counted in P&L) | `test_full_lifecycle...`, `test_overage...` |
| 9 | Supplier payment from empty/insufficient account; overpay | `purchase_service` | Major | no funds / balance checks | checks added (also purchase down-payment) | `TestSupplierPayments` |
| 10 | Sale-line functions had no permission check | `sales_service` | Major | UI-only protection | `require_permission` | `TestServiceLevelPermissions` |
| 11 | IMEI format not validated in services | `inventory_service`, `purchase_service` | Minor | UI-only | digits/length/IMEI1≠IMEI2/batch duplicates | `TestImeiIntegrity` |

## B. Test results
Full suite: **452 passed, 0 failed, 0 skipped** (3 third-party warnings). New file `tests/test_audit_sales.py` (+ migration test). Reproduction: the stock tests were run against the old code and failed (4 of 6).
Not run here: real printers, Windows `.exe`, a UI session on a real Windows desktop.

## C. Reconciliation (automated scenarios)
- Sale 350 paid with 400 cash: drawer +350, change 50, payments sum = total.
- Mixed vodafone 200 + cash 200: drawer +150, change 50.
- Credit sale + partial returns: customer balance and drawer move exactly as refunds dictate; refunds sum to the line total.
- Net profit = net revenue − cost of units that stayed sold; cash in − cash out = net revenue (`test_reconciles_with_the_ledgers`).
- Shift: expected cash == drawer book balance before close; after close the balance equals the count, the shortage appears once in P&L.
- Supplier: partial + full payments leave supplier, invoice and ledger consistent.

## D. Remaining risks / owner decisions
- Wallet/InstaPay payments on a sale do not change wallet balances (no wallet selector in the payment dialog).
- Concurrency tested with two sessions on one SQLite file; true multi-PC use of one file is not supported.
- Non-restocked returned devices keep status `sold`.
- Hardware printing, Arabic print layout on real printers, Windows packaging: manual testing needed.
- UI audit was limited to smoke/flow tests; no manual walkthrough of every screen.

## E. Release readiness
Financial rules and data integrity: improved and covered by tests. Not declared production-ready: hardware, Windows build and a manual UI pass are still open.


---
# Round 2 (2026-11-22)
| # | Issue | Fix | Tests |
|---|---|---|---|
| 12 | Used-device purchase: no balance check, not tied to the shift (Critical) | `_debit_account` + shift attribution | `TestUsedDevicePurchase` |
| 13 | IMEI rules differed between add / edit / invoice / used purchase (Critical) | `app.core.imei.clean_imei_pair` everywhere | `TestOneImeiRule` |
| 14 | Frozen Windows/PyInstaller app crashed at start (`logging.config` missing) (Critical) | hidden imports in spec; complete build script | verified by a real build + start in this environment (Linux) |
| 15 | Any text accepted as payment method (High) | closed list | `TestPaymentAndRefundMethods` |
| 16 | Any text accepted as refund method; non-cash refunds unrecorded; void of wallet sale paid cash (High) | closed list; cash back only up to cash received | `TestRefundGoesBackTheWayItCame` |
| 17 | `sale.remaining` stale after returns (High) | derived from unpaid-at-sale minus returned value | `TestRemainingAfterReturns` |
| 18 | No whole-cycle reconciliation test (High) | `tests/test_full_cycle.py` | passes |
| 19 | Old-database backup/restore/upgrade untested (High) | `test_old_database_with_real_data_survives...` | passes |

Windows: the build was run here on Linux (same spec); it exposed the crash above and the fixed build starts, migrates and seeds. A run of `packaging\build_windows.bat` on a clean Windows PC is still required.
