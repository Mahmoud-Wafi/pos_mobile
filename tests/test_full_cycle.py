"""One whole shop cycle through the services, then every ledger is reconciled against the others."""
import pytest
from sqlalchemy import func

from app.core import clock
from app.core.money import egp_to_piasters as egp
from app.models.accounting import CashAccount, CashTransaction
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.sale import Sale
from app.models.stock import Device, StockMovement
from app.services import (accounting_service, customer_service, inventory_service, purchase_service,
                          report_service, sales_service, shift_service)
from app.services.sales_profit import net_sales_profit

from tests.test_sales import cashier, manager  # noqa: F401  (fixtures)


def _drawer(s):
    return s.query(CashAccount).filter_by(type="drawer").first()


def test_whole_cycle_reconciles(db_session, manager, cashier):
    s = db_session
    # ── set-up ───────────────────────────────────────────────────────────────
    charger = inventory_service.create_product(s, manager, {
        "name": "Charger", "type": "accessory", "cost_price": egp("100"), "sale_price": egp("150"),
        "min_price": egp("120"), "min_stock": 1, "track_imei": False, "warranty_days": 30})
    phone = inventory_service.create_product(s, manager, {
        "name": "Phone", "type": "phone", "cost_price": egp("4000"), "sale_price": egp("5000"),
        "min_price": egp("4200"), "min_stock": 0, "track_imei": True, "warranty_days": 365})
    customer = customer_service.create_customer(s, manager, {"name": "Ali", "credit_limit": egp("20000")})
    supplier = purchase_service.create_supplier(s, manager, name="Sup", phone="0100")
    s.commit()
    shift = shift_service.open_shift(s, cashier, opening_cash=egp("10000"))
    s.commit()
    drawer = _drawer(s)
    assert accounting_service.verify_drawer_balance_integrity(s, drawer.id)

    # ── purchases: 20 chargers (500 paid, 1500 owed) + 1 phone (paid in full) ─
    inv1 = purchase_service.create_purchase(
        s, manager, supplier_id=supplier.id, invoice_number="P1",
        items_data=[{"product_id": charger.id, "quantity": 20, "unit_cost": egp("100")}], paid_amount=egp("500"))
    inv2 = purchase_service.create_purchase(
        s, manager, supplier_id=supplier.id, invoice_number="P2",
        items_data=[{"product_id": phone.id, "quantity": 1, "unit_cost": egp("4000"),
                     "imeis": [{"imei1": "352001111222333"}]}], paid_amount=egp("4000"))
    purchase_service.pay_supplier(s, manager, supplier.id, egp("1000"), purchase_id=inv1.id)
    purchase_service.record_used_device_purchase(
        s, manager, "أحمد محمد علي حسن", "29001011234567", "01012345678", phone.id, "352001111222341", egp("1000"))
    s.commit()
    assert supplier.balance == egp("500") == inv1.balance + inv2.balance

    # ── sales ────────────────────────────────────────────────────────────────
    s1 = sales_service.start_sale(s, cashier)
    i1 = sales_service.add_line(s, cashier, s1, charger, quantity=4)                       # 600, paid with 700 cash
    sales_service.post_sale(s, cashier, s1, [{"method": "cash", "amount": egp("700")}])
    dev = inventory_service.get_devices_for_product(s, phone.id, status="in_stock")[0]
    s2 = sales_service.start_sale(s, cashier, customer_id=customer.id)
    sales_service.add_line(s, cashier, s2, phone, device=dev)                              # 5000: 2000 cash 3000 credit
    sales_service.post_sale(s, cashier, s2, [{"method": "cash", "amount": egp("2000")},
                                             {"method": "credit", "amount": egp("3000")}])
    s3 = sales_service.start_sale(s, cashier)
    sales_service.add_line(s, cashier, s3, charger, quantity=2)                            # 300 by vodafone
    sales_service.post_sale(s, cashier, s3, [{"method": "vodafone", "amount": egp("300")}])
    s.commit()

    # ── returns / void / expense ─────────────────────────────────────────────
    sales_service.return_sale_items(s, cashier, s1.id, [{"sale_item_id": i1.id, "quantity": 1}], reason="defect")
    shift_service.open_shift(s, manager, opening_cash=0)
    sales_service.void_sale(s, manager, s3.id, "customer cancelled")
    cat = accounting_service.create_expense_category(s, manager, "Misc")
    accounting_service.add_expense(s, cashier, cat.id, egp("50"), drawer.id)
    s.commit()

    # ── reconciliation ───────────────────────────────────────────────────────
    # 1. drawer book balance == its ledger, and == what the open shift expects
    assert accounting_service.verify_drawer_balance_integrity(s, drawer.id)
    expected = shift_service.calculate_expected_cash(s, shift.id)
    assert expected == drawer.balance
    # 2. stock == movements, for accessories and for phones
    for product in (charger, phone):
        moved = s.query(func.coalesce(func.sum(StockMovement.quantity), 0)).filter_by(product_id=product.id).scalar()
        assert product.current_quantity() == moved, product.name
    assert s.query(Device).filter_by(product_id=phone.id, status="in_stock").count() == phone.current_quantity()
    # 3. supplier and customer balances == their open invoices
    assert supplier.balance == sum(p.balance for p in s.query(Purchase).filter_by(supplier_id=supplier.id))
    assert customer.balance == sum(x.remaining for x in s.query(Sale).filter_by(customer_id=customer.id,
                                                                                status="posted")) == egp("3000")
    # 4. profit from first principles: revenue - cost of what stayed sold
    start, end = clock.day_bounds_utc(clock.local_today(), clock.local_today())
    sp = net_sales_profit(s, start, end)
    sold_cost = 3 * egp("100") + egp("4000")                       # 3 chargers stayed sold + the phone (the vouchers voided)
    assert sp["net_revenue"] == 3 * egp("150") + egp("5000")
    assert sp["net_profit"] == sp["net_revenue"] - sold_cost
    assert report_service.profit_report(s, manager)["sales_profit"] == sp["net_profit"]
    # 5. close the shift on the exact count: no shortage, ledger still consistent
    closed = shift_service.close_shift(s, cashier, shift.id, actual_cash=expected)
    s.commit()
    assert closed.diff == 0 and accounting_service.verify_drawer_balance_integrity(s, drawer.id)
