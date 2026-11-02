"""Tests for Phase 3 — Sales, POS, shifts, atomic posting, returns, and warranty.

Acceptance criteria:
  - Cannot sell an IMEI twice
  - Posting is atomic (simulated mid-way failure leaves DB unchanged)
  - Return restores stock and cash correctly
  - Profit per line matches cost snapshot
  - Min price & discount limits enforced
  - Warranty lookup and calculation
  - Thermal receipt & PDF invoice generated
"""
import pytest
import datetime
from decimal import Decimal
from pathlib import Path

from app.core.money import egp_to_piasters
from app.core.permissions import ROLE_MANAGER, ROLE_CASHIER
from app.core.security import hash_password
from app.models.user import User, Role
from app.models.product import Category, Product
from app.models.stock import Device, Stock
from app.models.customer import Customer
from app.models.accounting import CashAccount
from app.models.sale import Sale, SaleItem
from app.services import sales_service, shift_service, customer_service, inventory_service
from app.printing.receipt import generate_thermal_receipt_text, generate_warranty_invoice_pdf


@pytest.fixture
def manager(db_session):
    role = db_session.query(Role).filter_by(name=ROLE_MANAGER).first()
    u = User(username="mgr_sales", password_hash=hash_password("123"), full_name="Sales Mgr", role_id=role.id, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def cashier(db_session):
    role = db_session.query(Role).filter_by(name=ROLE_CASHIER).first()
    u = User(username="csh_sales", password_hash=hash_password("123"), full_name="Sales Cashier", role_id=role.id, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def active_shift(db_session, cashier):
    shift = shift_service.open_shift(db_session, cashier, opening_cash=egp_to_piasters("1000"))
    db_session.commit()
    return shift


@pytest.fixture
def phone_product(db_session, manager):
    cat = inventory_service.create_category(db_session, manager, "Phones")
    p = inventory_service.create_product(db_session, manager, {
        "name": "iPhone 15",
        "type": "phone",
        "cost_price": egp_to_piasters("40000"),
        "sale_price": egp_to_piasters("46000"),
        "min_price": egp_to_piasters("44000"),
        "min_stock": 1,
        "track_imei": True,
        "warranty_days": 365,
    })
    db_session.commit()
    return p


@pytest.fixture
def accessory_product(db_session, manager):
    cat = inventory_service.create_category(db_session, manager, "Accessories")
    p = inventory_service.create_product(db_session, manager, {
        "name": "Fast Charger",
        "type": "accessory",
        "cost_price": egp_to_piasters("200"),
        "sale_price": egp_to_piasters("350"),
        "min_price": egp_to_piasters("300"),
        "min_stock": 2,
        "track_imei": False,
        "warranty_days": 90,
    })
    # Add initial stock: 10 units
    inventory_service.adjust_stock(db_session, manager, p, 10, "Initial Stock")
    db_session.commit()
    return p


@pytest.fixture
def real_customer(db_session, manager):
    cust = customer_service.create_customer(db_session, manager, {
        "name": "أحمد محمود",
        "phone": "01012345678",
        "credit_limit": egp_to_piasters("10000"),
    })
    db_session.commit()
    return cust


# ── Acceptance Criterion 1: Cannot Sell an IMEI Twice ─────────────────────────

class TestIMEISales:
    def test_cannot_sell_same_imei_twice(self, db_session, manager, cashier, active_shift, phone_product):
        # 1. Add device (done by manager/inventory)
        devices = inventory_service.add_devices(db_session, manager, phone_product, [
            {"imei1": "352001111222333", "condition": "new", "purchase_cost": egp_to_piasters("40000")}
        ])
        device = devices[0]
        db_session.commit()

        # 2. First sale -> posts successfully
        sale1 = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale1, phone_product, device=device)
        sales_service.post_sale(db_session, cashier, sale1, [{"method": "cash", "amount": sale1.total}])
        db_session.commit()

        assert device.status == "sold"
        assert phone_product.current_quantity() == 0

        # 3. Second sale trying to sell the same device -> MUST FAIL
        sale2 = sales_service.start_sale(db_session, cashier)
        with pytest.raises(sales_service.DeviceNotAvailableError):
            sales_service.add_line(db_session, cashier, sale2, phone_product, device=device)

    def test_cannot_post_if_device_became_sold(self, db_session, manager, cashier, active_shift, phone_product):
        devices = inventory_service.add_devices(db_session, manager, phone_product, [
            {"imei1": "352009999888777", "condition": "new"}
        ])
        device = devices[0]
        db_session.commit()

        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, phone_product, device=device)

        # External change: device sold elsewhere
        device.status = "sold"
        db_session.flush()

        with pytest.raises(sales_service.DeviceNotAvailableError):
            sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])


# ── Acceptance Criterion 2: Posting is Atomic ─────────────────────────────────

class TestAtomicPosting:
    def test_atomic_posting_rollback_on_failure(self, db_session, manager, cashier, active_shift, phone_product, accessory_product):
        # Add a device (by manager)
        devices = inventory_service.add_devices(db_session, manager, phone_product, [
            {"imei1": "888888888888888", "condition": "new"}
        ])
        device = devices[0]
        db_session.commit()

        drawer = db_session.query(CashAccount).filter_by(type="drawer").first()
        initial_drawer_cash = drawer.balance
        initial_accessory_stock = accessory_product.current_quantity()

        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, phone_product, device=device)
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=2)

        # Simulate a crash/failure during posting (e.g. invalid credit customer)
        # Default "عميل نقدي" cannot receive credit!
        default_cust = customer_service.get_default_customer(db_session)
        sale.customer_id = default_cust.id

        # Attempt to post with only partial cash and remainder on credit
        with pytest.raises(sales_service.SaleError):
            sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": 1000}])
            db_session.commit()

        # Rollback session as done in service handlers
        db_session.rollback()

        # VERIFY ATOMIC INTEGRITY:
        db_session.expire_all()
        # 1. Device is STILL in_stock!
        dev_check = db_session.get(Device, device.id)
        assert dev_check.status == "in_stock"
        # 2. Accessory stock is UNTOUCHED!
        acc_check = db_session.get(Product, accessory_product.id)
        assert acc_check.current_quantity() == initial_accessory_stock
        # 3. Drawer cash is UNTOUCHED!
        drw_check = db_session.query(CashAccount).filter_by(type="drawer").first()
        assert drw_check.balance == initial_drawer_cash


# ── Acceptance Criterion 3: Return Restores Stock and Cash Correctly ──────────

class TestReturns:
    def test_return_restores_stock_and_cash(self, db_session, cashier, active_shift, accessory_product):
        initial_stock = accessory_product.current_quantity()  # 10
        drawer = db_session.query(CashAccount).filter_by(type="drawer").first()
        initial_cash = drawer.balance

        # 1. Sale of 3 chargers
        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=3)
        sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])
        db_session.commit()

        assert accessory_product.current_quantity() == initial_stock - 3
        assert drawer.balance == initial_cash + sale.total

        # 2. Return 1 charger
        sale_item = sale.items[0]
        ret = sales_service.return_sale_items(
            db_session, cashier, sale.id,
            return_items_data=[{"sale_item_id": sale_item.id, "quantity": 1}],
            reason="غير متوافق مع هاتف العميل",
            restock=True,
            refund_method="cash",
        )
        db_session.commit()

        # Restock verified: stock increased by 1
        assert accessory_product.current_quantity() == initial_stock - 2
        # Cash reversal verified: drawer decreased by price of 1 charger
        assert drawer.balance == (initial_cash + sale.total) - ret.refund_amount
        assert ret.refund_amount == sale_item.unit_price

    def test_return_phone_restores_device_in_stock(self, db_session, manager, cashier, active_shift, phone_product):
        devices = inventory_service.add_devices(db_session, manager, phone_product, [
            {"imei1": "777777777777777", "condition": "new"}
        ])
        device = devices[0]
        db_session.commit()

        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, phone_product, device=device)
        sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])
        db_session.commit()
        assert device.status == "sold"

        # Return phone
        sale_item = sale.items[0]
        sales_service.return_sale_items(
            db_session, cashier, sale.id,
            return_items_data=[{"sale_item_id": sale_item.id, "quantity": 1}],
            reason="استبدال بلون آخر",
            restock=True,
        )
        db_session.commit()

        assert device.status == "in_stock"
        assert phone_product.current_quantity() == 1


# ── Acceptance Criterion 4: Profit per Line Matches Cost Snapshot ──────────────

class TestProfitCalculation:
    def test_line_profit_matches_cost_snapshot(self, db_session, manager, cashier, active_shift, phone_product, accessory_product):
        devices = inventory_service.add_devices(db_session, manager, phone_product, [
            {"imei1": "666666666666666", "purchase_cost": egp_to_piasters("41000"), "extra_cost": egp_to_piasters("500")}
        ])
        device = devices[0]  # total cost = 41,500 EGP
        db_session.commit()

        sale = sales_service.start_sale(db_session, cashier)
        # Phone: sale price 46,000, cost 41,500 -> profit = 4,500 EGP (450,000 piasters)
        it_phone = sales_service.add_line(db_session, cashier, sale, phone_product, device=device)
        # Accessory: sale price 350, cost 200, qty 2 -> profit = (350*2) - (200*2) = 300 EGP (30,000 piasters)
        it_acc = sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=2)

        sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])
        db_session.commit()

        assert it_phone.unit_cost == egp_to_piasters("41500")
        assert it_phone.profit == egp_to_piasters("4500")

        assert it_acc.unit_cost == egp_to_piasters("200")
        assert it_acc.profit == egp_to_piasters("300")

        # Total invoice profit
        assert sale.total_profit == egp_to_piasters("4800")


# ── Business Rules: Min Price, Discounts, Shift, Credit ───────────────────────

class TestBusinessRules:
    def test_cannot_sell_without_open_shift(self, db_session, cashier, accessory_product):
        # No shift opened
        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, accessory_product)
        with pytest.raises(sales_service.ShiftRequiredError):
            sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])

    def test_below_min_price_requires_manager(self, db_session, cashier, active_shift, accessory_product, manager):
        # min_price is 300 EGP (30,000 piasters). Cashier tries to sell at 250 EGP.
        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, accessory_product, unit_price=egp_to_piasters("250"))

        # Cashier alone fails
        with pytest.raises(sales_service.PriceBelowMinimumError):
            sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])

        # With manager override -> succeeds
        posted = sales_service.post_sale(
            db_session, cashier, sale, [{"method": "cash", "amount": sale.total}],
            manager_override=manager,
        )
        assert posted.status == "posted"

    def test_discount_above_limit_requires_manager(self, db_session, cashier, active_shift, accessory_product, manager):
        sale = sales_service.start_sale(db_session, cashier)
        # subtotal: 350 EGP
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=1)

        # Cashier limit is 5% (17.50 EGP). Try applying 50 EGP discount.
        with pytest.raises(sales_service.DiscountLimitExceededError):
            sales_service.apply_discount(db_session, cashier, sale, egp_to_piasters("50"))

        # Manager can apply
        sales_service.apply_discount(db_session, cashier, sale, egp_to_piasters("50"), manager_override=manager)
        assert sale.discount == egp_to_piasters("50")

    def test_split_payment_with_credit_and_collection(self, db_session, cashier, active_shift, accessory_product, real_customer):
        sale = sales_service.start_sale(db_session, cashier, customer_id=real_customer.id)
        # 3 chargers = 1,050 EGP
        sales_service.add_line(db_session, cashier, sale, accessory_product, quantity=3)

        # Split: 500 cash + remainder (550) credit
        sales_service.post_sale(db_session, cashier, sale, [
            {"method": "cash", "amount": egp_to_piasters("500")},
            {"method": "credit", "amount": egp_to_piasters("550")},
        ])
        db_session.commit()

        assert real_customer.balance == egp_to_piasters("550")

        # Collect debt
        customer_service.collect_payment(db_session, cashier, real_customer.id, egp_to_piasters("550"), shift_id=active_shift.id)
        db_session.commit()

        assert real_customer.balance == 0


# ── Warranty Search & Invoices ────────────────────────────────────────────────

class TestWarrantyAndPrinting:
    def test_warranty_search_and_receipt_generation(self, db_session, manager, cashier, active_shift, phone_product, tmp_path):
        devices = inventory_service.add_devices(db_session, manager, phone_product, [
            {"imei1": "999000111222333", "condition": "new"}
        ])
        device = devices[0]
        db_session.commit()

        sale = sales_service.start_sale(db_session, cashier)
        sales_service.add_line(db_session, cashier, sale, phone_product, device=device)
        sales_service.post_sale(db_session, cashier, sale, [{"method": "cash", "amount": sale.total}])
        db_session.commit()

        # Warranty search by IMEI
        results = sales_service.search_warranty(db_session, "999000111222333")
        assert len(results) == 1
        assert results[0]["is_valid"] is True
        assert results[0]["warranty_days"] == 365

        # Thermal receipt text
        receipt_text = generate_thermal_receipt_text(sale)
        assert sale.invoice_no in receipt_text
        assert "999000111222333" in receipt_text

        # PDF warranty certificate
        pdf_path = tmp_path / f"invoice_{sale.invoice_no}.pdf"
        generate_warranty_invoice_pdf(sale, pdf_path)
        assert pdf_path.exists()
        assert pdf_path.stat().st_size > 0
