"""Inventory service — public API for all inventory operations.

Business rules (AGENTS.md §6):
- IMEI products: one Device per IMEI; duplicate IMEI → raises DuplicateIMEI.
- Accessories/cards: stock quantity tracked in Stock row.
- adjust_stock / stocktake both create StockMovement with type 'adjust'.
- stock quantity always equals sum of its movements (enforced in DB via this service).
- weighted_average cost_price updated on every purchase (called from purchase_service later;
  exposed here for single-responsibility and testing).
- low_stock returns products whose quantity <= min_stock.
- Permissions enforced: PERM_INVENTORY_EDIT required for mutations.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.money import weighted_average_cost
from app.core.permissions import (
    PERM_COST_VIEW, PERM_INVENTORY_EDIT, PERM_INVENTORY_VIEW, PERM_INVENTORY_ADJUST,
    require_permission,
)
from app.i18n import ar
from app.models.product import Brand, Category, Product, ProductBarcode
from app.models.purchase import PurchaseItem, UsedDevicePurchase
from app.models.sale import SaleItem
from app.models.stock import Device, Stock, StockMovement
from app.models.user import User


# ── Custom exceptions ─────────────────────────────────────────────────────────

class DuplicateIMEI(Exception):
    def __init__(self, imei: str):
        self.imei = imei
        super().__init__(f"IMEI مكرر: {imei}")


class ProductNotFound(Exception):
    pass


class InvalidProductType(Exception):
    pass


class InsufficientStock(Exception):
    pass


class InventoryError(Exception):
    """Business error with an Arabic message."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_stock_row(session: Session, product: Product) -> Stock:
    """Return (or create) the Stock row for a non-IMEI product."""
    if product.stock is None:
        stock = Stock(product_id=product.id, quantity=0)
        session.add(stock)
        session.flush()
        product.stock = stock
    return product.stock


def _add_movement(
    session: Session,
    product: Product,
    movement_type: str,
    quantity: int,
    user_id: Optional[int] = None,
    device: Optional[Device] = None,
    ref_type: Optional[str] = None,
    ref_id: Optional[int] = None,
    note: Optional[str] = None,
) -> StockMovement:
    mv = StockMovement(
        product_id=product.id,
        device_id=device.id if device else None,
        type=movement_type,
        quantity=quantity,
        user_id=user_id,
        ref_type=ref_type,
        ref_id=ref_id,
        note=note,
    )
    session.add(mv)
    return mv


# ── Barcodes ──────────────────────────────────────────────────────────────────

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_INTERNAL_CODE = re.compile(r"^P(\d{6})$")          # the fallback code printed on labels (label_service)


def normalize_barcode(text: str | None) -> str:
    """Trim, turn Arabic-Indic digits into Western ones and drop spaces / scanner line breaks."""
    return "".join((text or "").translate(_AR_DIGITS).split())


def find_product_by_barcode(session: Session, code: str) -> Optional[Product]:
    """The product that owns this barcode: main barcode, any extra barcode, or its internal label code."""
    code = normalize_barcode(code)
    if not code:
        return None
    product = session.query(Product).filter(Product.barcode == code).first()
    if product is None:
        extra = session.query(ProductBarcode).filter(ProductBarcode.code == code).first()
        product = extra.product if extra else None
    if product is None:
        m = _INTERNAL_CODE.match(code)
        if m:
            product = session.get(Product, int(m.group(1)))
    return product


def generate_barcode(session: Session) -> str:
    """A random, unused in-store EAN-13 code (prefix 2 = reserved for store use), e.g. for new products."""
    import random
    while True:
        body = "2" + "".join(random.choice("0123456789") for _ in range(11))
        check = (10 - sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(body)) % 10) % 10
        code = body + str(check)
        if find_product_by_barcode(session, code) is None:
            return code


def _check_barcode_free(session: Session, code: str, product_id: Optional[int]) -> None:
    owner = find_product_by_barcode(session, code)
    if owner is not None and owner.id != product_id and not _INTERNAL_CODE.match(code):
        raise InventoryError(ar.PRODUCT_BARCODE_TAKEN)


def set_extra_barcodes(session: Session, product: Product, codes: list[str]) -> None:
    """Replace the product's extra barcodes. Each code must be free (not used by another product)."""
    wanted: list[str] = []
    for raw in codes:
        code = normalize_barcode(raw)
        if code and code != product.barcode and code not in wanted:
            _check_barcode_free(session, code, product.id)
            wanted.append(code)
    keep = {b.code: b for b in product.extra_barcodes}
    for code, row in list(keep.items()):
        if code not in wanted:
            product.extra_barcodes.remove(row)
    for code in wanted:
        if code not in keep:
            product.extra_barcodes.append(ProductBarcode(code=code))
    session.flush()


# ── Category & Brand ──────────────────────────────────────────────────────────

def create_category(session: Session, user: User, name: str, parent_id: Optional[int] = None) -> Category:
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    cat = Category(name=name, parent_id=parent_id, created_by=user.id)
    session.add(cat)
    session.flush()
    return cat


def create_brand(session: Session, user: User, name: str) -> Brand:
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    brand = Brand(name=name, created_by=user.id)
    session.add(brand)
    session.flush()
    return brand


# ── Products ──────────────────────────────────────────────────────────────────

def create_product(session: Session, user: User, data: dict) -> Product:
    """Create a product and its Stock row (quantity=0).

    data keys: name, type, cost_price, sale_price, min_price, min_stock,
               track_imei, warranty_days, barcode, category_id, brand_id
    """
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)

    product_type = data.get("type", "accessory")
    if product_type not in ("phone", "accessory", "card"):
        raise InvalidProductType(f"نوع المنتج غير صحيح: {product_type}")

    barcode = normalize_barcode(data.get("barcode")) or None
    if barcode:
        _check_barcode_free(session, barcode, None)
    product = Product(
        name=data["name"],
        type=product_type,
        barcode=barcode,
        category_id=data.get("category_id"),
        brand_id=data.get("brand_id"),
        cost_price=int(data.get("cost_price", 0)),
        sale_price=int(data.get("sale_price", 0)),
        min_price=int(data.get("min_price", 0)),
        min_stock=int(data.get("min_stock", 0)),
        track_imei=bool(data.get("track_imei", False)),
        warranty_days=int(data.get("warranty_days", 0)),
        is_active=bool(data.get("is_active", True)),
        created_by=user.id,
    )
    session.add(product)
    session.flush()

    # Always create a Stock row (for IMEI products it reflects device count)
    _ensure_stock_row(session, product)
    if data.get("extra_barcodes"):
        set_extra_barcodes(session, product, list(data["extra_barcodes"]))

    log_action(session, "create_product", user_id=user.id,
               table_name="products", record_id=product.id,
               new_value={"name": product.name, "type": product.type})
    return product


def product_has_history(session: Session, product: Product) -> bool:
    """True when the product appears in sales, purchases, devices or the stock ledger."""
    pid = product.id
    return bool(
        session.query(SaleItem.id).filter(SaleItem.product_id == pid).first()
        or session.query(PurchaseItem.id).filter(PurchaseItem.product_id == pid).first()
        or session.query(Device.id).filter(Device.product_id == pid).first()
        or session.query(StockMovement.id).filter(StockMovement.product_id == pid).first()
    )


def update_product(session: Session, user: User, product_id: int, data: dict) -> Product:
    """Edit a product. Cost needs ``cost.view``; type / IMEI tracking are locked once it has history."""
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    product = session.get(Product, product_id)
    if product is None:
        raise ProductNotFound(f"المنتج {product_id} غير موجود")
    if "name" in data and not str(data["name"]).strip():
        raise InventoryError(ar.PRODUCT_NAME_REQUIRED)
    for money in ("sale_price", "min_price", "cost_price", "min_stock", "warranty_days"):
        if money in data and int(data[money]) < 0:
            raise InventoryError(ar.INV_NEGATIVE_VALUE)
    if "cost_price" in data:
        require_permission(user.permission_codes(), PERM_COST_VIEW, user.username)
    if ("type" in data and data["type"] != product.type) or \
            ("track_imei" in data and bool(data["track_imei"]) != product.track_imei):
        if product_has_history(session, product):
            raise InventoryError(ar.PRODUCT_TYPE_LOCKED)
        if "type" in data and data["type"] not in ("phone", "accessory", "card"):
            raise InvalidProductType(f"نوع المنتج غير صحيح: {data['type']}")
    if "barcode" in data:
        data = {**data, "barcode": normalize_barcode(data["barcode"]) or None}
        if data["barcode"]:
            _check_barcode_free(session, data["barcode"], product.id)
    old = {"name": product.name, "sale_price": product.sale_price, "cost_price": product.cost_price}
    for field in ("name", "barcode", "type", "category_id", "brand_id", "sale_price", "min_price",
                  "cost_price", "min_stock", "warranty_days", "track_imei", "is_active"):
        if field in data:
            value = data[field]
            if field == "name":
                value = str(value).strip()
            if field == "barcode":
                value = value or None
            setattr(product, field, value)
    if "extra_barcodes" in data:
        set_extra_barcodes(session, product, list(data["extra_barcodes"]))
    log_action(session, "update_product", user_id=user.id,
               table_name="products", record_id=product.id,
               old_value=old, new_value={k: v for k, v in data.items()})
    session.flush()
    return product


def delete_product(session: Session, user: User, product_id: int) -> None:
    """Permanently delete a product that was never used. Anything with history must be deactivated instead."""
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    product = session.get(Product, product_id)
    if product is None:
        raise ProductNotFound(f"المنتج {product_id} غير موجود")
    if product_has_history(session, product):
        raise InventoryError(ar.PRODUCT_HAS_HISTORY)
    stock = session.query(Stock).filter_by(product_id=product.id).first()
    if stock is not None and stock.quantity:
        raise InventoryError(ar.PRODUCT_HAS_HISTORY)
    name = product.name
    if stock is not None:
        session.delete(stock)
    session.delete(product)
    log_action(session, "delete_product", user_id=user.id, table_name="products", record_id=product_id,
               old_value={"name": name})
    session.flush()


# ── Devices / IMEI ────────────────────────────────────────────────────────────

def _check_imei_unique(session: Session, imei: str) -> None:
    """Raise DuplicateIMEI if this IMEI already exists in any device row."""
    if not imei:
        return
    exists = (
        session.query(Device)
        .filter((Device.imei1 == imei) | (Device.imei2 == imei))
        .first()
    )
    if exists:
        raise DuplicateIMEI(imei)


def add_devices(session: Session, user: User, product: Product, devices_data: list[dict]) -> list[Device]:
    """Add one or more IMEI devices to a product.

    Each dict in devices_data: imei1, imei2 (opt), condition, purchase_cost, extra_cost, notes.
    Raises DuplicateIMEI on collision (entire batch rolled back).
    """
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    if not product.track_imei:
        raise InvalidProductType("هذا المنتج لا يُتتبع بـ IMEI")

    created: list[Device] = []
    for d in devices_data:
        imei1 = str(d["imei1"]).strip()
        imei2 = str(d["imei2"]).strip() if d.get("imei2") else None

        _check_imei_unique(session, imei1)
        if imei2:
            _check_imei_unique(session, imei2)

        device = Device(
            product_id=product.id,
            imei1=imei1,
            imei2=imei2,
            condition=d.get("condition", "new"),
            purchase_cost=int(d.get("purchase_cost", product.cost_price)),
            extra_cost=int(d.get("extra_cost", 0)),
            status="in_stock",
            notes=d.get("notes"),
            created_by=user.id,
        )
        session.add(device)
        session.flush()

        # Stock movement: purchase +1
        _add_movement(session, product, "purchase", 1, user_id=user.id,
                      device=device, note=f"IMEI: {imei1}")
        created.append(device)

    # Update stock quantity to match device count
    stock = _ensure_stock_row(session, product)
    stock.quantity = session.query(func.count(Device.id)).filter(
        Device.product_id == product.id, Device.status == "in_stock"
    ).scalar() or 0

    log_action(session, "add_devices", user_id=user.id,
               table_name="devices", record_id=product.id,
               new_value={"count": len(created), "imeis": [d.imei1 for d in created]})
    return created


def _sync_stock_quantity(session: Session, product: Product) -> None:
    stock = _ensure_stock_row(session, product)
    stock.quantity = session.query(func.count(Device.id)).filter(
        Device.product_id == product.id, Device.status == "in_stock").scalar() or 0


def _device_has_history(session: Session, device: Device) -> bool:
    """Linked to a purchase, a sale or a used-device intake (so it is part of the books)."""
    return bool(device.purchase_id or device.sale_item_id or device.status != "in_stock"
                or session.query(UsedDevicePurchase.id).filter(UsedDevicePurchase.device_id == device.id).first()
                or session.query(SaleItem.id).filter(SaleItem.device_id == device.id).first())


def update_device(session: Session, user: User, device_id: int, data: dict) -> Device:
    """Edit a device. Sold / returned devices only accept notes; IMEI and costs only while in stock."""
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    device = session.get(Device, device_id)
    if device is None:
        raise InventoryError(ar.DEVICE_NOT_FOUND)
    editable_all = device.status == "in_stock"
    locked = {"imei1", "imei2", "condition", "purchase_cost", "extra_cost"} & set(data)
    if locked and not editable_all:
        raise InventoryError(ar.DEVICE_LOCKED)
    if ("purchase_cost" in data or "extra_cost" in data):
        require_permission(user.permission_codes(), PERM_COST_VIEW, user.username)
        if int(data.get("purchase_cost", 0)) < 0 or int(data.get("extra_cost", 0)) < 0:
            raise InventoryError(ar.INV_NEGATIVE_VALUE)
    old = {"imei1": device.imei1, "imei2": device.imei2, "condition": device.condition}
    for field in ("imei1", "imei2"):
        if field in data:
            value = (str(data[field]).strip() if data[field] else None)
            if field == "imei1" and not value:
                raise InventoryError(ar.DEVICE_IMEI_REQUIRED)
            if value and value != getattr(device, field):
                _check_imei_unique(session, value)
            setattr(device, field, value)
    if "condition" in data:
        if data["condition"] not in ("new", "used"):
            raise InventoryError(ar.INV_NEGATIVE_VALUE)
        device.condition = data["condition"]
    for field in ("purchase_cost", "extra_cost"):
        if field in data:
            setattr(device, field, int(data[field]))
    if "notes" in data:
        device.notes = (data["notes"] or "").strip() or None
    log_action(session, "update_device", user_id=user.id, table_name="devices", record_id=device.id,
               old_value=old, new_value={k: v for k, v in data.items()})
    session.flush()
    return device


def delete_device(session: Session, user: User, device_id: int) -> None:
    """Delete a device that was added by mistake (in stock, never bought, sold or taken in).

    Its own ledger row goes with it, so the stock count stays right. Anything else must be written off.
    """
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    device = session.get(Device, device_id)
    if device is None:
        raise InventoryError(ar.DEVICE_NOT_FOUND)
    if _device_has_history(session, device):
        raise InventoryError(ar.DEVICE_HAS_HISTORY)
    product, imei = device.product, device.imei1
    session.query(StockMovement).filter(StockMovement.device_id == device.id).delete()
    session.delete(device)
    session.flush()
    _sync_stock_quantity(session, product)
    log_action(session, "delete_device", user_id=user.id, table_name="devices", record_id=device_id,
               old_value={"imei1": imei, "product": product.name})


def write_off_device(session: Session, user: User, device_id: int, reason: str) -> Device:
    """Take an in-stock device out of stock (damaged / lost) while keeping its history."""
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    device = session.get(Device, device_id)
    if device is None:
        raise InventoryError(ar.DEVICE_NOT_FOUND)
    if device.status != "in_stock":
        raise InventoryError(ar.DEVICE_LOCKED)
    if not (reason or "").strip():
        raise InventoryError(ar.DEVICE_REASON_REQUIRED)
    device.status = "damaged"
    device.notes = ((device.notes + "\n") if device.notes else "") + f"{ar.DEVICE_WRITTEN_OFF}: {reason.strip()}"
    _add_movement(session, device.product, "adjust", -1, user_id=user.id, device=device,
                  note=f"{ar.DEVICE_WRITTEN_OFF}: {reason.strip()}")
    session.flush()
    _sync_stock_quantity(session, device.product)
    log_action(session, "write_off_device", user_id=user.id, table_name="devices", record_id=device.id,
               new_value={"reason": reason.strip(), "imei1": device.imei1})
    return device


# ── Stock lookup ──────────────────────────────────────────────────────────────

def find_by_barcode_or_imei(session: Session, query: str) -> Optional[Product | Device]:
    """Find a product by barcode, or a device by IMEI1/IMEI2."""
    query = query.strip()
    # Try IMEI first
    device = session.query(Device).filter(
        (Device.imei1 == query) | (Device.imei2 == query)
    ).first()
    if device:
        return device
    # Try barcode (main, extra, or the internal label code)
    return find_product_by_barcode(session, query)


def get_all_products(session: Session, active_only: bool = True):
    q = session.query(Product)
    if active_only:
        q = q.filter(Product.is_active == True)
    return q.order_by(Product.name).all()


def get_devices_for_product(session: Session, product_id: int, status: Optional[str] = None):
    """Devices of a product, oldest first (FIFO: sell the oldest unit first)."""
    q = session.query(Device).filter(Device.product_id == product_id)
    if status:
        q = q.filter(Device.status == status)
    return q.order_by(Device.created_at, Device.id).all()


def search_products(session: Session, text: str, limit: int = 50) -> list[Product]:
    """Type-ahead search over active products by name or barcode."""
    text = (text or "").strip()
    if not text:
        return []
    like = f"%{text}%"
    return (
        session.query(Product)
        .filter(Product.is_active == True)  # noqa: E712
        .filter((Product.name.ilike(like)) | (Product.barcode.like(like))
                | Product.id.in_(session.query(ProductBarcode.product_id).filter(ProductBarcode.code.like(like))))
        .order_by(Product.name)
        .limit(limit)
        .all()
    )


# ── Stock adjustment & stocktake ─────────────────────────────────────────────

def adjust_stock(
    session: Session,
    user: User,
    product: Product,
    new_quantity: int,
    reason: str,
) -> StockMovement:
    """Set stock to new_quantity by creating a signed 'adjust' movement.

    Rules:
    - new_quantity < 0 requires PERM_INVENTORY_ADJUST and manager flag (caller responsibility).
    - For IMEI products adjustments are blocked (stock = device count).
    """
    require_permission(user.permission_codes(), PERM_INVENTORY_ADJUST, user.username)
    if product.track_imei:
        raise InvalidProductType("تعديل المخزون يدويًا غير مسموح للمنتجات المتتبعة بـ IMEI")

    stock = _ensure_stock_row(session, product)
    diff = new_quantity - stock.quantity
    if diff == 0:
        raise ValueError("الكمية الجديدة تساوي الكمية الحالية، لا يوجد تغيير")

    mv = _add_movement(session, product, "adjust", diff, user_id=user.id, note=reason)
    stock.quantity = new_quantity

    log_action(session, "adjust_stock", user_id=user.id,
               table_name="stock", record_id=stock.id,
               old_value={"quantity": stock.quantity - diff},
               new_value={"quantity": new_quantity},
               reason=reason)
    session.flush()
    return mv


def stocktake(
    session: Session,
    user: User,
    product: Product,
    actual_quantity: int,
    reason: str = "جرد مخزون",
) -> Optional[StockMovement]:
    """Record a physical stock count.

    If actual differs from system quantity → creates an 'adjust' movement.
    Returns None if quantities match.
    """
    require_permission(user.permission_codes(), PERM_INVENTORY_ADJUST, user.username)
    if product.track_imei:
        raise InvalidProductType("الجرد اليدوي غير متاح لمنتجات الـ IMEI")

    stock = _ensure_stock_row(session, product)
    diff = actual_quantity - stock.quantity
    if diff == 0:
        return None

    mv = _add_movement(session, product, "adjust", diff, user_id=user.id,
                       note=f"{reason} | من {stock.quantity} إلى {actual_quantity}")
    stock.quantity = actual_quantity

    log_action(session, "stocktake", user_id=user.id,
               table_name="stock", record_id=stock.id,
               old_value={"quantity": actual_quantity - diff},
               new_value={"quantity": actual_quantity},
               reason=reason)
    session.flush()
    return mv


# ── Weighted average cost (called by purchase_service, exposed here for testing) ──

def update_weighted_average_cost(
    session: Session,
    product: Product,
    new_qty_purchased: int,
    new_unit_cost: int,
) -> int:
    """Recalculate weighted average cost_price after a purchase.

    Returns new average cost_price (piasters).
    """
    stock = _ensure_stock_row(session, product)
    old_qty = stock.quantity
    new_avg = weighted_average_cost(old_qty, product.cost_price, new_qty_purchased, new_unit_cost)
    product.cost_price = new_avg
    session.flush()
    return new_avg


# ── Low stock ─────────────────────────────────────────────────────────────────

def low_stock(session: Session) -> list[Product]:
    """Return active products whose current quantity <= min_stock."""
    products = session.query(Product).filter(Product.is_active == True).all()
    result = []
    for p in products:
        qty = p.current_quantity()
        if qty <= p.min_stock:
            result.append(p)
    return result


# ── Stock integrity check ─────────────────────────────────────────────────────

def stock_matches_movements(session: Session, product: Product) -> bool:
    """Verify stock.quantity == sum of all movements for non-IMEI products."""
    if product.track_imei:
        # For IMEI: check stock == count of in_stock devices
        in_stock_count = session.query(func.count(Device.id)).filter(
            Device.product_id == product.id, Device.status == "in_stock"
        ).scalar() or 0
        stock = _ensure_stock_row(session, product)
        return stock.quantity == in_stock_count

    total = session.query(func.sum(StockMovement.quantity)).filter(
        StockMovement.product_id == product.id
    ).scalar() or 0
    stock = _ensure_stock_row(session, product)
    return stock.quantity == total

