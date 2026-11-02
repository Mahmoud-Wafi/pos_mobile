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

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.money import weighted_average_cost
from app.core.permissions import (
    PERM_INVENTORY_EDIT, PERM_INVENTORY_VIEW, PERM_INVENTORY_ADJUST,
    require_permission,
)
from app.models.product import Brand, Category, Product
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

    product = Product(
        name=data["name"],
        type=product_type,
        barcode=data.get("barcode"),
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

    log_action(session, "create_product", user_id=user.id,
               table_name="products", record_id=product.id,
               new_value={"name": product.name, "type": product.type})
    return product


def update_product(session: Session, user: User, product_id: int, data: dict) -> Product:
    require_permission(user.permission_codes(), PERM_INVENTORY_EDIT, user.username)
    product = session.get(Product, product_id)
    if product is None:
        raise ProductNotFound(f"المنتج {product_id} غير موجود")
    old = {"name": product.name, "sale_price": product.sale_price}
    for field in ("name", "barcode", "category_id", "brand_id", "sale_price",
                  "min_price", "min_stock", "warranty_days", "is_active"):
        if field in data:
            setattr(product, field, data[field])
    log_action(session, "update_product", user_id=user.id,
               table_name="products", record_id=product.id,
               old_value=old, new_value=data)
    session.flush()
    return product


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
    # Try barcode
    product = session.query(Product).filter_by(barcode=query).first()
    return product


def get_all_products(session: Session, active_only: bool = True):
    q = session.query(Product)
    if active_only:
        q = q.filter(Product.is_active == True)
    return q.order_by(Product.name).all()


def get_devices_for_product(session: Session, product_id: int, status: Optional[str] = None):
    q = session.query(Device).filter(Device.product_id == product_id)
    if status:
        q = q.filter(Device.status == status)
    return q.all()


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

