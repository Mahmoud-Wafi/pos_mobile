"""Tests for Phase 4: Purchases, Suppliers, Weighted-Average Cost, and Used Devices."""
from __future__ import annotations

import os
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from app.core.money import egp_to_piasters, piasters_to_egp
from app.core.permissions import PermissionDenied
from app.core.permissions import ROLE_MANAGER, ROLE_CASHIER
from app.core.security import hash_password
from app.models.accounting import CashAccount
from app.models.product import Product
from app.models.purchase import Supplier, Purchase, UsedDevicePurchase
from app.models.stock import Device, Stock
from app.models.user import User, Role
from app.services import purchase_service, inventory_service


@pytest.fixture
def manager_user(db_session: Session) -> User:
    role = db_session.query(Role).filter_by(name=ROLE_MANAGER).first()
    u = User(username="mgr_purchases", password_hash=hash_password("123"), full_name="Purchases Mgr", role_id=role.id, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def cashier_user(db_session: Session) -> User:
    role = db_session.query(Role).filter_by(name=ROLE_CASHIER).first()
    u = User(username="csh_purchases", password_hash=hash_password("123"), full_name="Purchases Cashier", role_id=role.id, is_active=True)
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def drawer_account(db_session: Session) -> CashAccount:
    drawer = db_session.query(CashAccount).filter(CashAccount.type == "drawer").first()
    if not drawer:
        drawer = CashAccount(name="الدرج الرئيسي", type="drawer", balance=egp_to_piasters(50000))
        db_session.add(drawer)
        db_session.commit()
    else:
        drawer.balance = egp_to_piasters(50000)
        db_session.commit()
    return drawer


@pytest.fixture
def phone_product(db_session: Session, manager_user: User) -> Product:
    p = inventory_service.create_product(
        db_session,
        manager_user,
        {
            "name": "Samsung Galaxy S24 Ultra",
            "type": "phone",
            "cost_price": egp_to_piasters(45000),
            "sale_price": egp_to_piasters(52000),
            "min_price": egp_to_piasters(48000),
            "min_stock": 2,
            "track_imei": True,
            "warranty_days": 365,
        },
    )
    db_session.commit()
    return p


@pytest.fixture
def accessory_product(db_session: Session, manager_user: User) -> Product:
    p = inventory_service.create_product(
        db_session,
        manager_user,
        {
            "name": "Anker 30W Fast Charger",
            "type": "accessory",
            "cost_price": egp_to_piasters(200),
            "sale_price": egp_to_piasters(350),
            "min_price": egp_to_piasters(250),
            "min_stock": 5,
            "track_imei": False,
        },
    )
    # Give initial stock of 10 units at 200 EGP
    stock = db_session.query(Stock).filter(Stock.product_id == p.id).first()
    stock.quantity = 10
    db_session.commit()
    return p


class TestWeightedAverageCost:
    """Test weighted-average unit cost updates on accessory purchases."""

    def test_weighted_average_updates_accurately(
        self,
        db_session: Session,
        manager_user: User,
        accessory_product: Product,
        drawer_account: CashAccount,
    ):
        supplier = purchase_service.create_supplier(
            db_session, manager_user, name="Al-Ahram Accessories", phone="01011112222"
        )
        db_session.commit()

        # Initial: 10 units @ 200 EGP = 2000 EGP
        # Buy 10 units @ 300 EGP = 3000 EGP
        # New expected cost: (10 * 200 + 10 * 300) / 20 = 250 EGP (25,000 piasters)
        items = [
            {
                "product_id": accessory_product.id,
                "quantity": 10,
                "unit_cost": egp_to_piasters(300),
            }
        ]

        purchase = purchase_service.create_purchase(
            db_session,
            manager_user,
            supplier_id=supplier.id,
            invoice_number="INV-ACC-001",
            items_data=items,
            paid_amount=egp_to_piasters(3000),
        )
        db_session.commit()

        db_session.refresh(accessory_product)
        stock = db_session.query(Stock).filter(Stock.product_id == accessory_product.id).first()

        assert stock.quantity == 20
        assert accessory_product.cost_price == egp_to_piasters(250)
        assert purchase.total == egp_to_piasters(3000)
        assert purchase.paid == egp_to_piasters(3000)
        assert purchase.balance == 0


class TestSupplierBalance:
    """Test supplier balance integrity: supplier balance = purchases - payments."""

    def test_supplier_balance_reconciliation(
        self,
        db_session: Session,
        manager_user: User,
        accessory_product: Product,
        drawer_account: CashAccount,
    ):
        supplier = purchase_service.create_supplier(
            db_session, manager_user, name="Cairo Distribution Co", phone="01200003333"
        )
        db_session.commit()
        assert supplier.balance == 0

        # Purchase 1: 5,000 EGP total, 2,000 EGP paid, 3,000 EGP on credit
        items1 = [
            {
                "product_id": accessory_product.id,
                "quantity": 25,
                "unit_cost": egp_to_piasters(200),
            }
        ]
        p1 = purchase_service.create_purchase(
            db_session,
            manager_user,
            supplier_id=supplier.id,
            invoice_number="INV-SUP-101",
            items_data=items1,
            paid_amount=egp_to_piasters(2000),
        )
        db_session.commit()

        db_session.refresh(supplier)
        assert p1.balance == egp_to_piasters(3000)
        assert supplier.balance == egp_to_piasters(3000)

        # Separate Supplier Payment: Pay 1,500 EGP
        pay = purchase_service.pay_supplier(
            db_session,
            manager_user,
            supplier_id=supplier.id,
            amount=egp_to_piasters(1500),
            note="Partial debt payment",
        )
        db_session.commit()

        db_session.refresh(supplier)
        assert supplier.balance == egp_to_piasters(1500)

        # Purchase 2: 10,000 EGP total, 0 paid
        items2 = [
            {
                "product_id": accessory_product.id,
                "quantity": 50,
                "unit_cost": egp_to_piasters(200),
            }
        ]
        p2 = purchase_service.create_purchase(
            db_session,
            manager_user,
            supplier_id=supplier.id,
            invoice_number="INV-SUP-102",
            items_data=items2,
            paid_amount=0,
        )
        db_session.commit()

        db_session.refresh(supplier)
        # Previous balance (1500) + New purchase unpaid (10000) = 11500 EGP
        assert supplier.balance == egp_to_piasters(11500)

        # Verify invariant: total purchases (15,000) - all payments (2,000 + 1,500 = 3,500) = 11,500
        all_purchases_total = sum(p.total for p in supplier.purchases)
        all_payments_total = sum(pmt.amount for pmt in supplier.payments)
        assert supplier.balance == (all_purchases_total - all_payments_total)


class TestPhonePurchasesAndIMEI:
    """Test purchasing phones with IMEI tracking."""

    def test_purchase_phones_creates_in_stock_devices(
        self,
        db_session: Session,
        manager_user: User,
        phone_product: Product,
        drawer_account: CashAccount,
    ):
        supplier = purchase_service.create_supplier(
            db_session, manager_user, name="Delta Mobile Wholesale", phone="01122223333"
        )
        db_session.commit()

        items = [
            {
                "product_id": phone_product.id,
                "quantity": 2,
                "unit_cost": egp_to_piasters(42000),
                "imeis": [
                    {"imei1": "860011223344551", "imei2": "860011223344552"},
                    {"imei1": "860011223344553", "imei2": None},
                ],
            }
        ]

        purchase = purchase_service.create_purchase(
            db_session,
            manager_user,
            supplier_id=supplier.id,
            invoice_number="INV-PHONE-001",
            items_data=items,
            paid_amount=egp_to_piasters(84000),
        )
        db_session.commit()

        # Check devices created
        dev1 = db_session.query(Device).filter(Device.imei1 == "860011223344551").first()
        dev2 = db_session.query(Device).filter(Device.imei1 == "860011223344553").first()

        assert dev1 is not None
        assert dev1.status == "in_stock"
        assert dev1.condition == "new"
        assert dev1.purchase_cost == egp_to_piasters(42000)
        assert dev1.purchase_id == purchase.id

        assert dev2 is not None
        assert dev2.status == "in_stock"

        # Check product stock count matches
        assert phone_product.current_quantity() == 2

    def test_duplicate_imei_in_purchase_blocked(
        self,
        db_session: Session,
        manager_user: User,
        phone_product: Product,
        drawer_account: CashAccount,
    ):
        supplier = purchase_service.create_supplier(
            db_session, manager_user, name="Tech Importers", phone="01555554444"
        )
        db_session.commit()

        # Attempt to insert same IMEI twice in batch
        items = [
            {
                "product_id": phone_product.id,
                "quantity": 2,
                "unit_cost": egp_to_piasters(40000),
                "imeis": [
                    {"imei1": "990011223344556"},
                    {"imei1": "990011223344556"},
                ],
            }
        ]

        with pytest.raises(purchase_service.DuplicateIMEIError):
            purchase_service.create_purchase(
                db_session,
                manager_user,
                supplier_id=supplier.id,
                invoice_number="INV-DUP-01",
                items_data=items,
            )


class TestUsedDevicePurchase:
    """Test used-device purchase flow and legal declaration generation."""

    def test_used_device_enters_stock_with_used_condition(
        self,
        db_session: Session,
        manager_user: User,
        phone_product: Product,
        drawer_account: CashAccount,
    ):
        drawer_before = drawer_account.balance

        used = purchase_service.record_used_device_purchase(
            db_session,
            manager_user,
            seller_name="أحمد محمود حسن إبراهيم",
            seller_national_id="29501011234567",
            seller_phone="01099887766",
            product_id=phone_product.id,
            imei1="352011998877665",
            imei2="352011998877666",
            price=egp_to_piasters(32000),
            condition_notes="حالة ممتازة، بطارية 95%، بدون خدوش",
        )
        db_session.commit()

        assert used.id is not None
        assert used.device.condition == "used"
        assert used.device.status == "in_stock"
        assert used.device.purchase_cost == egp_to_piasters(32000)
        assert used.device.imei1 == "352011998877665"

        # Check drawer cash decreased
        db_session.refresh(drawer_account)
        assert drawer_account.balance == drawer_before - egp_to_piasters(32000)

        # Check declaration generation
        pdf_path = purchase_service.generate_declaration(
            db_session,
            manager_user,
            used.id,
            dest_path="/tmp/test_used_declaration.pdf",
        )
        assert Path(pdf_path).exists()
        assert Path(pdf_path).stat().st_size > 1000
        assert used.declaration_printed is True

    def test_invalid_national_id_rejected(
        self,
        db_session: Session,
        manager_user: User,
        phone_product: Product,
        drawer_account: CashAccount,
    ):
        # 13 digits instead of 14
        with pytest.raises(purchase_service.PurchaseError, match="14"):
            purchase_service.record_used_device_purchase(
                db_session,
                manager_user,
                seller_name="علي مصطفى",
                seller_national_id="2950101123456",  # 13 digits
                seller_phone="01112345678",
                product_id=phone_product.id,
                imei1="352011998877111",
                price=egp_to_piasters(15000),
            )


class TestPermissions:
    """Test permission enforcement on purchase operations."""

    def test_cashier_cannot_create_purchase(
        self,
        db_session: Session,
        cashier_user: User,
        accessory_product: Product,
    ):
        with pytest.raises(PermissionDenied):
            purchase_service.create_supplier(
                db_session, cashier_user, name="Forbidden Supplier"
            )

        with pytest.raises(PermissionDenied):
            purchase_service.create_purchase(
                db_session,
                cashier_user,
                supplier_id=1,
                invoice_number="INV-NO-AUTH",
                items_data=[{"product_id": accessory_product.id, "quantity": 1, "unit_cost": 100}],
            )
