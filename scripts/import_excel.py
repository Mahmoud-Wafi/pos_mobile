"""Excel import script for inventory products.

Usage:
    python scripts/import_excel.py <path_to_excel_file>
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from decimal import Decimal
import openpyxl
from sqlalchemy.orm import Session

from app.core.database import get_session, session_scope
from app.core.money import egp_to_piasters
from app.models.user import User
from app.models.product import Category, Brand, Product
from app.services import inventory_service


def import_products_from_excel(file_path: Path | str, user_id: int | None = None) -> int:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"الملف غير موجود: {file_path}")

    wb = openpyxl.load_workbook(path, data_only=True)
    sheet = wb.active

    imported_count = 0
    with session_scope() as session:
        # Get admin user if user_id not provided
        if user_id:
            user = session.get(User, user_id)
        else:
            user = session.query(User).filter_by(username="admin").first()

        if not user:
            raise RuntimeError("مستخدم غير موجود لتنفيذ عملية الاستيراد")

        # Map header row
        headers = [str(cell.value).strip() if cell.value else "" for cell in sheet[1]]
        header_map = {name.lower(): idx for idx, name in enumerate(headers) if name}

        # Expected headers in Arabic or English
        def get_val(row, *aliases):
            for a in aliases:
                idx = header_map.get(a.lower())
                if idx is not None and idx < len(row):
                    val = row[idx].value
                    return val if val is not None else ""
            return ""

        for row_idx, row in enumerate(sheet.iter_rows(min_row=2), start=2):
            name = str(get_val(row, "name", "الاسم", "اسم المنتج")).strip()
            if not name:
                continue

            barcode = str(get_val(row, "barcode", "الباركود", "باركود")).strip() or None
            cat_name = str(get_val(row, "category", "القسم", "التصنيف")).strip()
            brand_name = str(get_val(row, "brand", "الماركة", "البراند")).strip()
            ptype = str(get_val(row, "type", "النوع")).strip() or "accessory"
            if ptype in ("هاتف", "موبايل", "phone"):
                ptype = "phone"
            elif ptype in ("كارت", "شحن", "card"):
                ptype = "card"
            else:
                ptype = "accessory"

            track_imei_val = str(get_val(row, "track_imei", "تتبع imei", "imei")).strip().lower()
            track_imei = track_imei_val in ("1", "true", "yes", "نعم") or ptype == "phone"

            cost_raw = get_val(row, "cost_price", "التكلفة", "سعر التكلفة") or 0
            sale_raw = get_val(row, "sale_price", "سعر البيع", "البيع") or 0
            min_p_raw = get_val(row, "min_price", "أقل سعر", "الحد الأدنى للسعر") or 0
            min_stock = int(get_val(row, "min_stock", "الحد الأدنى للمخزون") or 0)
            warranty = int(get_val(row, "warranty_days", "الضمان", "أيام الضمان") or 0)
            initial_stock = int(get_val(row, "quantity", "stock", "الكمية", "المخزون الأولي") or 0)

            cost_price = egp_to_piasters(Decimal(str(cost_raw)))
            sale_price = egp_to_piasters(Decimal(str(sale_raw)))
            min_price = egp_to_piasters(Decimal(str(min_p_raw)))

            # Category
            category_id = None
            if cat_name:
                cat = session.query(Category).filter_by(name=cat_name).first()
                if not cat:
                    cat = Category(name=cat_name, created_by=user.id)
                    session.add(cat)
                    session.flush()
                category_id = cat.id

            # Brand
            brand_id = None
            if brand_name:
                brand = session.query(Brand).filter_by(name=brand_name).first()
                if not brand:
                    brand = Brand(name=brand_name, created_by=user.id)
                    session.add(brand)
                    session.flush()
                brand_id = brand.id

            product_data = {
                "name": name,
                "barcode": barcode,
                "category_id": category_id,
                "brand_id": brand_id,
                "type": ptype,
                "cost_price": cost_price,
                "sale_price": sale_price,
                "min_price": min_price,
                "min_stock": min_stock,
                "track_imei": track_imei,
                "warranty_days": warranty,
                "is_active": True,
            }

            product = inventory_service.create_product(session, user, product_data)

            if initial_stock > 0 and not track_imei:
                inventory_service.adjust_stock(
                    session, user, product, initial_stock, reason="استيراد مخزون أولي من ملف Excel"
                )

            imported_count += 1

    return imported_count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("الاستخدام: python scripts/import_excel.py <path_to_file.xlsx>")
        sys.exit(1)
    file_arg = sys.argv[1]
    count = import_products_from_excel(file_arg)
    print(f"تم استيراد {count} منتج بنجاح.")

