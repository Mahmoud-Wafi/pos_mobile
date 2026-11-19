"""Excel / CSV import (products, devices) with preview + per-row errors, and .xlsx / CSV export.

Headers are accepted in Arabic or English (D-008). Money columns are in EGP and become integer
piasters through ``parse_egp_input`` (no floats). Import is two-step: ``preview_*`` validates every
row without touching the database; ``commit_*`` writes the valid rows in one transaction.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.imei import luhn_valid, normalize_imei
from app.core.money import parse_egp_input, piasters_to_input
from app.core.permissions import (
    PERM_COST_VIEW, PERM_INVENTORY_EDIT, PERM_INVENTORY_VIEW, PERM_REPORTS_VIEW, require_permission,
)
from app.models.product import Brand, Product, ProductBarcode
from app.models.stock import Device
from app.models.user import User
from app.services import inventory_service


class ImportExportError(Exception):
    """Business error with an Arabic message."""


# ── headers ───────────────────────────────────────────────────────────────────
# canonical key -> accepted header names (lower-cased on comparison)
PRODUCT_HEADERS: dict[str, list[str]] = {
    "name": ["name", "الاسم", "اسم الصنف", "اسم المنتج"],
    "type": ["type", "النوع"],
    "barcode": ["barcode", "الباركود"],
    "brand": ["brand", "الماركة", "العلامة التجارية"],
    "cost_price": ["cost_price", "cost", "سعر التكلفة", "التكلفة"],
    "sale_price": ["sale_price", "price", "سعر البيع", "السعر"],
    "min_price": ["min_price", "أقل سعر", "اقل سعر", "أدنى سعر"],
    "min_stock": ["min_stock", "الحد الأدنى", "حد الطلب"],
    "quantity": ["quantity", "qty", "الكمية"],
    "track_imei": ["track_imei", "imei", "تتبع imei", "تتبع السيريال"],
    "warranty_days": ["warranty_days", "warranty", "أيام الضمان", "ايام الضمان", "الضمان"],
}
DEVICE_HEADERS: dict[str, list[str]] = {
    "product": ["product", "الصنف", "المنتج", "اسم الصنف"],
    "barcode": ["barcode", "الباركود"],
    "imei1": ["imei1", "imei", "imei 1", "السيريال", "السيريال 1"],
    "imei2": ["imei2", "imei 2", "السيريال 2"],
    "condition": ["condition", "الحالة"],
    "purchase_cost": ["purchase_cost", "cost", "سعر الشراء", "التكلفة"],
}
PRODUCT_TEMPLATE_HEADERS = ["الاسم", "النوع", "الباركود", "الماركة", "سعر التكلفة", "سعر البيع", "أقل سعر",
                            "الحد الأدنى", "الكمية", "تتبع IMEI", "أيام الضمان"]
PRODUCT_TEMPLATE_EXAMPLE = ["سماعة بلوتوث", "اكسسوار", "6221234567890", "Anker", "150", "250", "200", "3", "10", "لا", "90"]
DEVICE_TEMPLATE_HEADERS = ["الصنف", "السيريال 1", "السيريال 2", "الحالة", "سعر الشراء"]
DEVICE_TEMPLATE_EXAMPLE = ["Samsung A15", "356938035643809", "", "جديد", "7500"]

_TYPES = {"phone": "phone", "هاتف": "phone", "موبايل": "phone", "جوال": "phone",
          "accessory": "accessory", "اكسسوار": "accessory", "إكسسوار": "accessory", "اكسسوارات": "accessory",
          "card": "card", "كارت": "card", "كروت": "card", "كارت شحن": "card"}
_YES = {"1", "yes", "y", "true", "نعم", "ايوه", "أيوه", "صح"}
_NO = {"0", "no", "n", "false", "لا", "", "خطأ"}
_CONDITIONS = {"new": "new", "جديد": "new", "used": "used", "مستعمل": "used", "استعمال": "used"}


# ── reading files ─────────────────────────────────────────────────────────────
def _cell_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def read_table(path: str | Path) -> tuple[list[str], list[list[str]]]:
    """Read the first sheet of an .xlsx or a .csv into (headers, rows) of text."""
    p = Path(path)
    if not p.exists():
        raise ImportExportError("الملف غير موجود")
    suffix = p.suffix.lower()
    try:
        if suffix in (".xlsx", ".xlsm"):
            wb = load_workbook(p, read_only=True, data_only=True)
            raw = [[_cell_text(c) for c in row] for row in wb.worksheets[0].iter_rows(values_only=True)]
            wb.close()
        elif suffix == ".csv":
            with open(p, encoding="utf-8-sig", newline="") as f:
                raw = [[c.strip() for c in row] for row in csv.reader(f)]
        else:
            raise ImportExportError("نوع الملف غير مدعوم؛ استخدم .xlsx أو .csv")
    except ImportExportError:
        raise
    except Exception as exc:
        raise ImportExportError("تعذر قراءة الملف؛ تأكد أنه ملف Excel أو CSV سليم") from exc
    raw = [r for r in raw if any(c for c in r)]
    if not raw:
        raise ImportExportError("الملف فارغ")
    return raw[0], raw[1:]


def _map_headers(headers: list[str], spec: dict[str, list[str]]) -> dict[str, int]:
    names = {h.strip().lower(): i for i, h in enumerate(headers)}
    out = {}
    for key, aliases in spec.items():
        for a in aliases:
            if a.lower() in names:
                out[key] = names[a.lower()]
                break
    return out


# ── preview model ─────────────────────────────────────────────────────────────
@dataclass
class RowResult:
    row_no: int                                   # 1-based line in the file (header is line 1)
    data: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ImportPreview:
    kind: str
    rows: list[RowResult]

    @property
    def valid(self) -> list[RowResult]:
        return [r for r in self.rows if r.ok]

    @property
    def invalid(self) -> list[RowResult]:
        return [r for r in self.rows if not r.ok]


def _get(row: list[str], cols: dict[str, int], key: str) -> str:
    i = cols.get(key)
    return row[i].strip() if i is not None and i < len(row) else ""


def _money(text: str, label: str, errors: list[str], default: int = 0) -> int:
    if text == "":
        return default
    try:
        return parse_egp_input(text)
    except (ValueError, ArithmeticError):
        errors.append(f"{label}: قيمة غير صحيحة ({text})")
        return default


def _int(text: str, label: str, errors: list[str], default: int = 0) -> int:
    if text == "":
        return default
    try:
        n = int(float(text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))))
        if n < 0:
            raise ValueError
        return n
    except ValueError:
        errors.append(f"{label}: رقم غير صحيح ({text})")
        return default


# ── products ──────────────────────────────────────────────────────────────────
def preview_products(session: Session, user: User, path: str | Path) -> ImportPreview:
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    headers, rows = read_table(path)
    cols = _map_headers(headers, PRODUCT_HEADERS)
    if "name" not in cols:
        raise ImportExportError("لم يتم العثور على عمود الاسم (name / الاسم) في الملف")
    existing_barcodes = {b for (b,) in session.query(Product.barcode).filter(Product.barcode.isnot(None))}
    existing_barcodes |= {c for (c,) in session.query(ProductBarcode.code)}
    seen_barcodes: set[str] = set()
    results: list[RowResult] = []
    for n, row in enumerate(rows, start=2):
        r = RowResult(n)
        name = _get(row, cols, "name")
        if not name:
            r.errors.append("الاسم مطلوب")
        ptype = _TYPES.get(_get(row, cols, "type").lower(), None) if _get(row, cols, "type") else "accessory"
        if ptype is None:
            r.errors.append(f"النوع غير معروف ({_get(row, cols, 'type')}) — استخدم: هاتف / اكسسوار / كارت")
        barcode = _get(row, cols, "barcode") or None
        if barcode:
            if barcode in existing_barcodes:
                r.errors.append(f"الباركود موجود بالفعل في المخزون ({barcode})")
            elif barcode in seen_barcodes:
                r.errors.append(f"الباركود مكرر داخل الملف ({barcode})")
            seen_barcodes.add(barcode)
        track_text = _get(row, cols, "track_imei").lower()
        if track_text in _YES:
            track = True
        elif track_text in _NO:
            track = ptype == "phone" and "track_imei" not in cols
        else:
            track = False
            r.errors.append(f"تتبع IMEI: قيمة غير صحيحة ({track_text}) — استخدم نعم / لا")
        cost = _money(_get(row, cols, "cost_price"), "سعر التكلفة", r.errors)
        sale = _money(_get(row, cols, "sale_price"), "سعر البيع", r.errors)
        min_price = _money(_get(row, cols, "min_price"), "أقل سعر", r.errors, default=cost)
        if sale and min_price > sale:
            r.errors.append("أقل سعر أكبر من سعر البيع")
        qty = _int(_get(row, cols, "quantity"), "الكمية", r.errors)
        if track and qty:
            r.warnings.append("الأصناف ذات IMEI تُضاف أجهزتها من ملف الأجهزة؛ تم تجاهل الكمية")
            qty = 0
        r.data = {
            "name": name, "type": ptype or "accessory", "barcode": barcode, "brand": _get(row, cols, "brand"),
            "cost_price": cost, "sale_price": sale, "min_price": min_price,
            "min_stock": _int(_get(row, cols, "min_stock"), "الحد الأدنى", r.errors),
            "quantity": qty, "track_imei": track,
            "warranty_days": _int(_get(row, cols, "warranty_days"), "أيام الضمان", r.errors),
        }
        results.append(r)
    return ImportPreview("products", results)


def commit_products(session: Session, user: User, preview: ImportPreview) -> int:
    """Create the valid rows of a products preview. Returns the number created."""
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    created = 0
    brands: dict[str, Brand] = {b.name.lower(): b for b in session.query(Brand).all()}
    for r in preview.valid:
        d = dict(r.data)
        brand_name = d.pop("brand")
        qty = d.pop("quantity")
        if brand_name:
            brand = brands.get(brand_name.lower())
            if brand is None:
                brand = inventory_service.create_brand(session, user, brand_name)
                brands[brand_name.lower()] = brand
            d["brand_id"] = brand.id
        product = inventory_service.create_product(session, user, d)
        if qty:
            inventory_service.adjust_stock(session, user, product, qty, "استيراد من ملف")
        created += 1
    log_action(session, "import_products", user_id=user.id, table_name="products",
               new_value={"created": created, "skipped": len(preview.invalid)})
    return created


# ── devices ───────────────────────────────────────────────────────────────────
def preview_devices(session: Session, user: User, path: str | Path) -> ImportPreview:
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    headers, rows = read_table(path)
    cols = _map_headers(headers, DEVICE_HEADERS)
    if "imei1" not in cols or ("product" not in cols and "barcode" not in cols):
        raise ImportExportError("الملف يجب أن يحتوي على عمود الصنف (أو الباركود) وعمود السيريال")
    by_name = {p.name.lower(): p for p in session.query(Product).filter(Product.track_imei.is_(True))}
    by_barcode = {p.barcode: p for p in session.query(Product).filter(Product.track_imei.is_(True)) if p.barcode}
    seen: set[str] = set()
    results: list[RowResult] = []
    for n, row in enumerate(rows, start=2):
        r = RowResult(n)
        product = by_barcode.get(_get(row, cols, "barcode")) or by_name.get(_get(row, cols, "product").lower())
        if product is None:
            r.errors.append("الصنف غير موجود أو لا يتتبع IMEI")
        imei1 = normalize_imei(_get(row, cols, "imei1"))
        imei2 = normalize_imei(_get(row, cols, "imei2"))
        for label, imei in (("السيريال 1", imei1), ("السيريال 2", imei2)):
            if not imei:
                if label == "السيريال 1":
                    r.errors.append("السيريال 1 مطلوب")
                continue
            if len(imei) != 15:
                r.errors.append(f"{label} يجب أن يكون 15 رقماً ({imei})")
            elif not luhn_valid(imei):
                r.warnings.append(f"{label} لا يجتاز فحص Luhn ({imei})")
            if imei in seen:
                r.errors.append(f"{label} مكرر داخل الملف ({imei})")
            elif session.query(Device.id).filter((Device.imei1 == imei) | (Device.imei2 == imei)).first():
                r.errors.append(f"{label} مسجل بالفعل في المخزون ({imei})")
            seen.add(imei)
        cond_text = _get(row, cols, "condition")
        cond = _CONDITIONS.get(cond_text.lower(), "new") if cond_text else "new"
        if cond_text and cond_text.lower() not in _CONDITIONS:
            r.errors.append(f"الحالة غير معروفة ({cond_text}) — استخدم جديد / مستعمل")
        cost = _money(_get(row, cols, "purchase_cost"), "سعر الشراء", r.errors,
                      default=product.cost_price if product else 0)
        r.data = {"product_id": product.id if product else None, "imei1": imei1, "imei2": imei2 or None,
                  "condition": cond, "purchase_cost": cost}
        results.append(r)
    return ImportPreview("devices", results)


def commit_devices(session: Session, user: User, preview: ImportPreview) -> int:
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    grouped: dict[int, list[dict]] = {}
    for r in preview.valid:
        grouped.setdefault(r.data["product_id"], []).append(r.data)
    created = 0
    for product_id, items in grouped.items():
        product = session.get(Product, product_id)
        created += len(inventory_service.add_devices(session, user, product, items))
    log_action(session, "import_devices", user_id=user.id, table_name="devices",
               new_value={"created": created, "skipped": len(preview.invalid)})
    return created


# ── template / xlsx writing ───────────────────────────────────────────────────
_HEAD_FILL = PatternFill("solid", fgColor="E2E8F0")


def _write_sheet(path: str | Path, title: str, headers: list[str], rows: Iterable[list], money_cols: set[int] = frozenset()) -> Path:
    """Write a real .xlsx with a right-to-left sheet, bold shaded header and frozen header row."""
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.sheet_view.rightToLeft = True
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = _HEAD_FILL
        c.alignment = Alignment(horizontal="center", vertical="center")
    count = 0
    for row in rows:
        ws.append(row)
        count += 1
    for ci in money_cols:
        for cell in ws.iter_cols(min_col=ci + 1, max_col=ci + 1, min_row=2, max_row=count + 1):
            for c in cell:
                c.number_format = "#,##0.00"
    ws.freeze_panes = "A2"
    for i, h in enumerate(headers, start=1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in ws.iter_rows(min_row=2, values_only=True) if r[i - 1] is not None] or [8])
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 4, 10), 50)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(p)
    return p


def write_template(kind: str, path: str | Path) -> Path:
    """Downloadable template for ``products`` or ``devices`` imports."""
    if kind == "products":
        return _write_sheet(path, "المنتجات", PRODUCT_TEMPLATE_HEADERS, [PRODUCT_TEMPLATE_EXAMPLE])
    if kind == "devices":
        return _write_sheet(path, "الأجهزة", DEVICE_TEMPLATE_HEADERS, [DEVICE_TEMPLATE_EXAMPLE])
    raise ImportExportError("نوع القالب غير معروف")


def _egp(piasters: int) -> float:
    return float(piasters_to_input(piasters))


# ── exports ───────────────────────────────────────────────────────────────────
def _write_any(path: str | Path, title: str, headers: list[str], rows: list[list], money_cols: set[int]) -> Path:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)
            for row in rows:
                w.writerow([f"{v:.2f}" if i in money_cols and isinstance(v, float) else v for i, v in enumerate(row)])
        return p
    return _write_sheet(p, title, headers, rows, money_cols)


def export_products(session: Session, user: User, path: str | Path) -> Path:
    require_permission(user.permission_codes(), PERM_INVENTORY_VIEW, user.username)
    show_cost = PERM_COST_VIEW in user.permission_codes()
    headers = ["الاسم", "النوع", "الباركود", "سعر البيع", "أقل سعر", "الكمية", "الحد الأدنى", "تتبع IMEI", "أيام الضمان"]
    money = {3, 4}
    if show_cost:
        headers.insert(3, "سعر التكلفة")
        money = {3, 4, 5}
    rows = []
    for p in session.query(Product).order_by(Product.name).all():
        row = [p.name, p.type, p.barcode or "", _egp(p.sale_price), _egp(p.min_price), p.current_quantity(),
               p.min_stock, "نعم" if p.track_imei else "لا", p.warranty_days]
        if show_cost:
            row.insert(3, _egp(p.cost_price))
        rows.append(row)
    return _write_any(path, "المنتجات", headers, rows, money)


def export_devices(session: Session, user: User, path: str | Path) -> Path:
    require_permission(user.permission_codes(), PERM_INVENTORY_VIEW, user.username)
    show_cost = PERM_COST_VIEW in user.permission_codes()
    headers = ["الصنف", "السيريال 1", "السيريال 2", "الحالة", "حالة المخزون"]
    money: set[int] = set()
    if show_cost:
        headers.append("سعر الشراء")
        money = {5}
    rows = []
    for d in session.query(Device).order_by(Device.id).all():
        row = [d.product.name, d.imei1, d.imei2 or "", "مستعمل" if d.condition == "used" else "جديد", d.status]
        if show_cost:
            row.append(_egp(d.total_cost))
        rows.append(row)
    return _write_any(path, "الأجهزة", headers, rows, money)


def export_report(user: User, report_data: dict, path: str | Path) -> Path:
    """Report rows (as produced by report_service) to .xlsx or .csv with the EGP columns as numbers."""
    require_permission(user.permission_codes(), PERM_REPORTS_VIEW, user.username)
    rows = report_data.get("rows") or report_data.get("customers") or []
    if not rows:
        return _write_any(path, "تقرير", ["لا توجد بيانات"], [], set())
    headers = list(rows[0].keys())
    money_keys = ("price", "total", "profit", "cost", "balance", "paid", "subtotal", "amount", "remaining")
    money = {i for i, h in enumerate(headers) if any(k in h for k in money_keys)}
    out = []
    for r in rows:
        out.append([_egp(v) if i in money and isinstance(v, int) else v for i, v in enumerate(r.values())])
    return _write_any(path, "تقرير", headers, out, money)
