"""Tests for Phase 2 — Inventory.

Acceptance criteria:
  - Cannot create duplicate IMEI (same product or different products, imei1 or imei2)
  - Stock always equals sum of movements (for non-IMEI), and count of in_stock devices (for IMEI)
  - Stocktake produces adjustment movements with correct difference
  - Low stock returns products whose quantity <= min_stock
  - Barcode generation works
  - Excel import works
"""
import pytest
from decimal import Decimal
from pathlib import Path

from app.core.money import egp_to_piasters
from app.core.permissions import PermissionDenied, ROLE_CASHIER, ROLE_MANAGER
from app.core.security import hash_password
from app.models.user import User, Role
from app.models.product import Category, Brand, Product
from app.models.stock import Device, Stock, StockMovement
from app.services import inventory_service
from app.utils.barcode_helper import generate_barcode_svg
from scripts.import_excel import import_products_from_excel


@pytest.fixture
def manager_user(db_session):
    role = db_session.query(Role).filter_by(name=ROLE_MANAGER).first()
    user = User(
        username="mgr_test",
        password_hash=hash_password("test"),
        full_name="Manager Test",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def cashier_user(db_session):
    role = db_session.query(Role).filter_by(name=ROLE_CASHIER).first()
    user = User(
        username="cashier_test",
        password_hash=hash_password("test"),
        full_name="Cashier Test",
        role_id=role.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def sample_phone(db_session, manager_user):
    cat = inventory_service.create_category(db_session, manager_user, "هواتف")
    brand = inventory_service.create_brand(db_session, manager_user, "Samsung")
    p = inventory_service.create_product(db_session, manager_user, {
        "name": "Galaxy S24",
        "barcode": "111111",
        "category_id": cat.id,
        "brand_id": brand.id,
        "type": "phone",
        "cost_price": egp_to_piasters("40000"),
        "sale_price": egp_to_piasters("45000"),
        "min_price": egp_to_piasters("43000"),
        "min_stock": 2,
        "track_imei": True,
        "warranty_days": 365,
    })
    db_session.commit()
    return p


@pytest.fixture
def sample_accessory(db_session, manager_user):
    cat = inventory_service.create_category(db_session, manager_user, "إكسسوار")
    p = inventory_service.create_product(db_session, manager_user, {
        "name": "كابل Type-C",
        "barcode": "222222",
        "category_id": cat.id,
        "type": "accessory",
        "cost_price": egp_to_piasters("100"),
        "sale_price": egp_to_piasters("150"),
        "min_price": egp_to_piasters("130"),
        "min_stock": 5,
        "track_imei": False,
        "warranty_days": 30,
    })
    db_session.commit()
    return p


class TestDeviceIMEI:
    def test_add_device_success(self, db_session, manager_user, sample_phone):
        devices = inventory_service.add_devices(db_session, manager_user, sample_phone, [
            {"imei1": "123456789012345", "imei2": "123456789012346", "condition": "new", "purchase_cost": 4000000}
        ])
        db_session.commit()
        assert len(devices) == 1
        assert sample_phone.current_quantity() == 1
        assert inventory_service.stock_matches_movements(db_session, sample_phone)

    def test_duplicate_imei_same_product_blocked(self, db_session, manager_user, sample_phone):
        inventory_service.add_devices(db_session, manager_user, sample_phone, [
            {"imei1": "123456789012345", "condition": "new"}
        ])
        db_session.commit()

        # Try to add exact same imei1 again
        with pytest.raises(inventory_service.DuplicateIMEI):
            inventory_service.add_devices(db_session, manager_user, sample_phone, [
                {"imei1": "123456789012345", "condition": "new"}
            ])

    def test_duplicate_imei_as_imei2_blocked(self, db_session, manager_user, sample_phone):
        inventory_service.add_devices(db_session, manager_user, sample_phone, [
            {"imei1": "111111111111111", "imei2": "222222222222222", "condition": "new"}
        ])
        db_session.commit()

        # Try to add imei1 with value of previous imei2
        with pytest.raises(inventory_service.DuplicateIMEI):
            inventory_service.add_devices(db_session, manager_user, sample_phone, [
                {"imei1": "222222222222222", "condition": "new"}
            ])

    def test_duplicate_imei_across_different_products_blocked(self, db_session, manager_user, sample_phone):
        inventory_service.add_devices(db_session, manager_user, sample_phone, [
            {"imei1": "999999999999999", "condition": "new"}
        ])
        db_session.commit()

        # Second phone product
        phone2 = inventory_service.create_product(db_session, manager_user, {
            "name": "Phone 2",
            "type": "phone",
            "track_imei": True,
        })
        db_session.commit()

        with pytest.raises(inventory_service.DuplicateIMEI):
            inventory_service.add_devices(db_session, manager_user, phone2, [
                {"imei1": "999999999999999", "condition": "new"}
            ])


class TestStockIntegrity:
    def test_stock_always_equals_sum_of_movements(self, db_session, manager_user, sample_accessory):
        # 1. Initial adjustment to 20
        inventory_service.adjust_stock(db_session, manager_user, sample_accessory, 20, "رصيد افتتاحي")
        db_session.commit()
        assert sample_accessory.current_quantity() == 20
        assert inventory_service.stock_matches_movements(db_session, sample_accessory)

        # 2. Adjust to 15 (diff -5)
        inventory_service.adjust_stock(db_session, manager_user, sample_accessory, 15, "تلف بعض القطع")
        db_session.commit()
        assert sample_accessory.current_quantity() == 15
        assert inventory_service.stock_matches_movements(db_session, sample_accessory)

        # 3. Adjust to 35 (diff +20)
        inventory_service.adjust_stock(db_session, manager_user, sample_accessory, 35, "تعديل مخزون")
        db_session.commit()
        assert sample_accessory.current_quantity() == 35
        assert inventory_service.stock_matches_movements(db_session, sample_accessory)


class TestStocktake:
    def test_stocktake_produces_adjustment_movement(self, db_session, manager_user, sample_accessory):
        # Set to 10
        inventory_service.adjust_stock(db_session, manager_user, sample_accessory, 10, "افتتاحي")
        db_session.commit()

        # Physical count is 8
        mv = inventory_service.stocktake(db_session, manager_user, sample_accessory, 8, "جرد نصف سنوي")
        db_session.commit()

        assert mv is not None
        assert mv.type == "adjust"
        assert mv.quantity == -2
        assert sample_accessory.current_quantity() == 8
        assert inventory_service.stock_matches_movements(db_session, sample_accessory)

    def test_stocktake_no_diff_returns_none(self, db_session, manager_user, sample_accessory):
        inventory_service.adjust_stock(db_session, manager_user, sample_accessory, 10, "افتتاحي")
        db_session.commit()

        mv = inventory_service.stocktake(db_session, manager_user, sample_accessory, 10, "جرد مطابق")
        assert mv is None
        assert sample_accessory.current_quantity() == 10

    def test_cashier_cannot_adjust_stock(self, db_session, cashier_user, sample_accessory):
        with pytest.raises(PermissionDenied):
            inventory_service.adjust_stock(db_session, cashier_user, sample_accessory, 5, "تعديل غير مصرح")


class TestLowStock:
    def test_low_stock_detection(self, db_session, manager_user, sample_accessory):
        # min_stock is 5
        inventory_service.adjust_stock(db_session, manager_user, sample_accessory, 4, "مخزون منخفض")
        db_session.commit()

        low = inventory_service.low_stock(db_session)
        assert sample_accessory in low

        # If increased above min_stock
        inventory_service.adjust_stock(db_session, manager_user, sample_accessory, 10, "توريد")
        db_session.commit()

        low = inventory_service.low_stock(db_session)
        assert sample_accessory not in low


class TestWeightedAverageCost:
    def test_weighted_average_updates(self, db_session, manager_user, sample_accessory):
        # Initial stock: 10 units @ 100 EGP (10,000 piasters)
        inventory_service.adjust_stock(db_session, manager_user, sample_accessory, 10, "افتتاحي")
        sample_accessory.cost_price = 10000
        db_session.commit()

        # Buy 10 units @ 200 EGP (20,000 piasters)
        # New avg = (10*10000 + 10*20000) / 20 = 15000 (150 EGP)
        new_avg = inventory_service.update_weighted_average_cost(
            db_session, sample_accessory, 10, 20000
        )
        db_session.commit()

        assert new_avg == 15000
        assert sample_accessory.cost_price == 15000


class TestBarcodeHelper:
    def test_generate_barcode_svg(self, tmp_path):
        out = generate_barcode_svg("622100012345", tmp_path, "test_barcode")
        assert out.exists()
        assert out.suffix == ".svg"
        assert out.stat().st_size > 0


class TestExcelImport:
    def test_import_products_from_excel(self, tmp_path, db_session, manager_user):
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["الاسم", "الباركود", "القسم", "البراند", "النوع", "سعر التكلفة", "سعر البيع", "أقل سعر", "الحد الأدنى للمخزون", "الكمية", "تتبع IMEI"])
        ws.append(["جراب آيفون 15", "555111222", "إكسسوارات", "Apple", "accessory", "50", "120", "100", "5", "25", "0"])
        ws.append(["شاحن سامسونج 25W", "555111333", "إكسسوارات", "Samsung", "accessory", "200", "350", "300", "4", "10", "0"])

        file_path = tmp_path / "products.xlsx"
        wb.save(file_path)

        count = import_products_from_excel(file_path, user_id=manager_user.id)
        assert count == 2

        p1 = db_session.query(Product).filter_by(barcode="555111222").first()
        assert p1 is not None
        assert p1.name == "جراب آيفون 15"
        assert p1.sale_price == 12000  # 120 EGP in piasters
        assert p1.current_quantity() == 25
