"""Demo data seeder for development and preview.

Usage:
    python scripts/seed_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import init_db, session_scope
from app.core.seed import seed_database
from app.core.money import egp_to_piasters
from app.models.user import User
from app.services import inventory_service


def seed_demo_data():
    init_db()
    with session_scope() as session:
        seed_database(session)

        admin = session.query(User).filter_by(username="admin").first()

        # Check if already seeded
        from app.models.product import Product
        if session.query(Product).count() > 0:
            print("البيانات التجريبية موجودة بالفعل.")
            return

        # 1. Categories
        cat_phones = inventory_service.create_category(session, admin, "هواتف ذكية")
        cat_acc = inventory_service.create_category(session, admin, "إكسسوارات")
        cat_cards = inventory_service.create_category(session, admin, "كروت شحن وباقات")

        # 2. Brands
        brand_samsung = inventory_service.create_brand(session, admin, "Samsung")
        brand_apple = inventory_service.create_brand(session, admin, "Apple")
        brand_xiaomi = inventory_service.create_brand(session, admin, "Xiaomi")
        brand_anker = inventory_service.create_brand(session, admin, "Anker")

        # 3. Products: Phones (IMEI tracked)
        p_s24 = inventory_service.create_product(session, admin, {
            "name": "Samsung Galaxy S24 Ultra 256GB",
            "barcode": "8806091234567",
            "category_id": cat_phones.id,
            "brand_id": brand_samsung.id,
            "type": "phone",
            "cost_price": egp_to_piasters("48000"),
            "sale_price": egp_to_piasters("52000"),
            "min_price": egp_to_piasters("50500"),
            "min_stock": 2,
            "track_imei": True,
            "warranty_days": 365,
        })

        p_iphone = inventory_service.create_product(session, admin, {
            "name": "iPhone 15 Pro 128GB",
            "barcode": "195949123456",
            "category_id": cat_phones.id,
            "brand_id": brand_apple.id,
            "type": "phone",
            "cost_price": egp_to_piasters("54000"),
            "sale_price": egp_to_piasters("58500"),
            "min_price": egp_to_piasters("57000"),
            "min_stock": 2,
            "track_imei": True,
            "warranty_days": 365,
        })

        p_redmi = inventory_service.create_product(session, admin, {
            "name": "Xiaomi Redmi Note 13 8/256",
            "barcode": "6941812700000",
            "category_id": cat_phones.id,
            "brand_id": brand_xiaomi.id,
            "type": "phone",
            "cost_price": egp_to_piasters("9200"),
            "sale_price": egp_to_piasters("10500"),
            "min_price": egp_to_piasters("10000"),
            "min_stock": 3,
            "track_imei": True,
            "warranty_days": 365,
        })

        # Add devices for phones
        inventory_service.add_devices(session, admin, p_s24, [
            {"imei1": "352001123456781", "imei2": "352001123456782", "condition": "new", "purchase_cost": egp_to_piasters("48000")},
            {"imei1": "352001123456783", "imei2": "352001123456784", "condition": "new", "purchase_cost": egp_to_piasters("48000")},
            {"imei1": "352001123456785", "condition": "used", "purchase_cost": egp_to_piasters("41000"), "notes": "حالة ممتازة مع العلبة"},
        ])

        inventory_service.add_devices(session, admin, p_iphone, [
            {"imei1": "353002234567891", "imei2": "353002234567892", "condition": "new", "purchase_cost": egp_to_piasters("54000")},
            {"imei1": "353002234567893", "condition": "new", "purchase_cost": egp_to_piasters("54000")},
        ])

        inventory_service.add_devices(session, admin, p_redmi, [
            {"imei1": "864003345678901", "imei2": "864003345678902", "condition": "new", "purchase_cost": egp_to_piasters("9200")},
        ])

        # 4. Products: Accessories
        p_charger = inventory_service.create_product(session, admin, {
            "name": "شاحن سريع Anker 30W Type-C",
            "barcode": "084806100001",
            "category_id": cat_acc.id,
            "brand_id": brand_anker.id,
            "type": "accessory",
            "cost_price": egp_to_piasters("450"),
            "sale_price": egp_to_piasters("650"),
            "min_price": egp_to_piasters("600"),
            "min_stock": 5,
            "track_imei": False,
            "warranty_days": 180,
        })
        inventory_service.adjust_stock(session, admin, p_charger, 15, "رصيد افتتاحي")

        p_cable = inventory_service.create_product(session, admin, {
            "name": "كابل شحن سريع Type-C to Type-C 1m",
            "barcode": "084806100002",
            "category_id": cat_acc.id,
            "brand_id": brand_anker.id,
            "type": "accessory",
            "cost_price": egp_to_piasters("120"),
            "sale_price": egp_to_piasters("200"),
            "min_price": egp_to_piasters("180"),
            "min_stock": 10,
            "track_imei": False,
            "warranty_days": 90,
        })
        # Low stock demo: stock is 3, min_stock is 10!
        inventory_service.adjust_stock(session, admin, p_cable, 3, "رصيد افتتاحي منخفض")

        p_airpods_case = inventory_service.create_product(session, admin, {
            "name": "جراب حماية سيليكون لسماعات AirPods Pro",
            "barcode": "084806100003",
            "category_id": cat_acc.id,
            "type": "accessory",
            "cost_price": egp_to_piasters("40"),
            "sale_price": egp_to_piasters("90"),
            "min_price": egp_to_piasters("75"),
            "min_stock": 5,
            "track_imei": False,
            "warranty_days": 0,
        })
        # Low stock demo: stock is 0 (created by default at 0)
        # inventory_service.adjust_stock not needed as it's already 0

        # 5. Products: Recharge Cards
        p_vf_100 = inventory_service.create_product(session, admin, {
            "name": "كارت فودافون فكة 100",
            "barcode": "622100011111",
            "category_id": cat_cards.id,
            "type": "card",
            "cost_price": egp_to_piasters("98"),
            "sale_price": egp_to_piasters("100"),
            "min_price": egp_to_piasters("100"),
            "min_stock": 20,
            "track_imei": False,
            "warranty_days": 0,
        })
        inventory_service.adjust_stock(session, admin, p_vf_100, 50, "رصيد افتتاحي")

        print("تم إضافة البيانات التجريبية بنجاح.")


if __name__ == "__main__":
    seed_demo_data()
