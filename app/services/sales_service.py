"""Sales service — POS operations, invoice posting, atomic transactions, returns, and warranty."""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from decimal import Decimal
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import clock
from app.core.audit import log_action
from app.core.money import percent_of
from app.core.money import piasters_to_input
from app.core.permissions import (
    PERM_SALES_CREATE, PERM_SALES_DISCOUNT, PERM_SALES_BELOW_MIN_PRICE,
    PERM_SALES_RETURN, PERM_SALES_VOID, ROLE_MANAGER,
    require_permission, has_permission,
)
from app.models.sale import Sale, SaleItem, SalePayment, SaleReturn, SaleReturnItem
from app.models.customer import Customer
from app.models.product import Product
from app.models.stock import Device, StockMovement
from app.models.shift import Shift
from app.models.accounting import CashAccount, CashTransaction
from app.models.user import User, Setting
from app.services import shift_service


# ── Exceptions ────────────────────────────────────────────────────────────────

class SaleError(Exception):
    pass


class DeviceNotAvailableError(SaleError):
    pass


class InsufficientStockError(SaleError):
    pass


class PriceBelowMinimumError(SaleError):
    pass


class DiscountLimitExceededError(SaleError):
    pass


class CreditLimitExceededError(SaleError):
    pass


class ShiftRequiredError(SaleError):
    pass


# Payment methods a sale may use; "credit" is the customer's account (debt). Anything else is refused.
PAYMENT_METHODS = frozenset({"cash", "vodafone", "orange", "etisalat", "instapay", "card", "bank", "credit"})
# A refund goes back by cash from the drawer, or by the non-cash method the customer paid with (recorded only).
REFUND_METHODS = PAYMENT_METHODS - {"credit"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _requested_by_product(sale: Sale, exclude_item_id: Optional[int] = None) -> dict[int, int]:
    """Total quantity of every non-IMEI product on the sale (several lines of one product add up)."""
    totals: dict[int, int] = {}
    for it in sale.items:
        if it.id is not None and it.id == exclude_item_id:
            continue
        if it.product is not None and not it.product.track_imei:
            totals[it.product_id] = totals.get(it.product_id, 0) + it.quantity
    return totals


def _lock_and_refresh_stock(session: Session, sale: Sale) -> None:
    """Take SQLite's write lock first, then re-read stock, so two sales cannot both spend the same units.

    A concurrent writer makes this fail ("database is locked") instead of overselling.
    """
    session.execute(Sale.__table__.update().where(Sale.id == sale.id).values(status=sale.status))
    for it in sale.items:
        if it.product is not None and it.product.stock is not None:
            session.refresh(it.product.stock)
        if it.device is not None:
            session.refresh(it.device)


def _generate_invoice_no(session: Session) -> str:
    """Generate sequential invoice number: INV-YYYYMMDD-####."""
    today_str = clock.local_now().strftime("%Y%m%d")
    prefix = f"INV-{today_str}-"
    last = (
        session.query(Sale.invoice_no)
        .filter(Sale.invoice_no.like(f"{prefix}%"))
        .order_by(Sale.id.desc())
        .first()
    )
    if last and last[0]:
        try:
            seq = int(last[0].split("-")[-1]) + 1
        except Exception:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def _generate_return_no(session: Session) -> str:
    """Generate sequential return number: RET-YYYYMMDD-####."""
    today_str = clock.local_now().strftime("%Y%m%d")
    prefix = f"RET-{today_str}-"
    last = (
        session.query(SaleReturn.return_no)
        .filter(SaleReturn.return_no.like(f"{prefix}%"))
        .order_by(SaleReturn.id.desc())
        .first()
    )
    if last and last[0]:
        try:
            seq = int(last[0].split("-")[-1]) + 1
        except Exception:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


def _get_cashier_discount_limit(session: Session) -> int:
    """Read cashier_discount_limit_pct setting (default 5%)."""
    st = session.query(Setting).filter_by(key="cashier_discount_limit_pct").first()
    if st and st.value:
        try:
            return int(st.value)
        except Exception:
            pass
    return 5


# ── Sales Draft & Lines ───────────────────────────────────────────────────────

def start_sale(
    session: Session,
    user: User,
    customer_id: Optional[int] = None,
    shift_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> Sale:
    """Create a new sale draft (held)."""
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)

    if customer_id is None:
        from app.services.customer_service import get_default_customer
        customer = get_default_customer(session)
        customer_id = customer.id

    if shift_id is None:
        active_shift = shift_service.get_active_shift(session, user.id)
        if active_shift:
            shift_id = active_shift.id

    invoice_no = _generate_invoice_no(session)
    sale = Sale(
        invoice_no=invoice_no,
        customer_id=customer_id,
        user_id=user.id,
        shift_id=shift_id,
        subtotal=0,
        discount=0,
        total=0,
        paid=0,
        remaining=0,
        status="held",
        notes=notes,
    )
    session.add(sale)
    session.flush()
    return sale


def add_line(
    session: Session,
    user: User,
    sale: Sale,
    product: Product,
    quantity: int = 1,
    unit_price: Optional[int] = None,
    device: Optional[Device] = None,
    discount: int = 0,
) -> SaleItem:
    """Add a product line to an unposted sale."""
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)
    if sale.status != "held":
        raise SaleError("لا يمكن تعديل فاتورة بعد حفظها نهائياً")

    if quantity <= 0:
        raise ValueError("الكمية يجب أن تكون أكبر من الصفر")

    price = unit_price if unit_price is not None else product.sale_price

    # Snapshot unit cost at time of sale
    if product.track_imei:
        if device is None:
            raise DeviceNotAvailableError("هذا المنتج يتطلب اختيار جهاز وسيريال (IMEI)")
        if device.status != "in_stock":
            raise DeviceNotAvailableError(f"الجهاز ذو السيريال {device.imei1} غير متوفر بالمخزن (حالته: {device.status})")
        if device.product_id != product.id:
            raise SaleError("الجهاز لا ينتمي لهذا الصنف")
        if any(it.device_id == device.id for it in sale.items):
            raise DeviceNotAvailableError(f"الجهاز بالسيريال {device.imei1} مضاف بالفعل في هذه الفاتورة")
        unit_cost = device.total_cost
        quantity = 1  # Each phone line is 1 device
    else:
        unit_cost = product.cost_price

    # Calculate warranty end date
    warranty_end = None
    if product.warranty_days > 0:
        warranty_end = utcnow() + datetime.timedelta(days=product.warranty_days)

    line_total = (price * quantity) - discount
    item = SaleItem(
        product_id=product.id,
        device_id=device.id if device else None,
        quantity=quantity,
        unit_price=price,
        unit_cost=unit_cost,
        discount=discount,
        line_total=line_total,
        warranty_end_date=warranty_end,
    )
    sale.items.append(item)
    session.flush()

    # Recalculate sale totals
    _recalculate_sale_totals(sale)
    return item


def remove_line(session: Session, user: User, sale: Sale, item_id: int) -> None:
    """Remove a line from an unposted sale."""
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)
    if sale.status != "held":
        raise SaleError("لا يمكن تعديل فاتورة بعد حفظها")

    item = session.get(SaleItem, item_id)
    if item and item.sale_id == sale.id:
        session.delete(item)
        session.flush()
        session.expire(sale, ["items"])   # drop the deleted row from the loaded collection
        _recalculate_sale_totals(sale)


def update_line(
    session: Session,
    user: User,
    sale: Sale,
    item_id: int,
    quantity: Optional[int] = None,
    unit_price: Optional[int] = None,
    discount: Optional[int] = None,
    manager_override: Optional[User] = None,
) -> SaleItem:
    """Edit quantity / unit price / line discount of a line on an unposted sale.

    * IMEI lines are always quantity 1.
    * Changing the unit price away from the catalogue price, or a line
      discount above the cashier limit, needs a manager (the user or
      ``manager_override``).
    """
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)
    if sale.status != "held":
        raise SaleError("لا يمكن تعديل فاتورة بعد حفظها")
    item = session.get(SaleItem, item_id)
    if item is None or item.sale_id != sale.id:
        raise SaleError("البند غير موجود في هذه الفاتورة")
    product = session.get(Product, item.product_id)
    is_manager = user.role.name == ROLE_MANAGER or (
        manager_override is not None and manager_override.role.name == ROLE_MANAGER
    )

    if quantity is not None:
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من الصفر")
        if product.track_imei and quantity != 1:
            raise SaleError("الجهاز المسجل بسيريال كميته 1 فقط")
        if not product.track_imei and not is_manager:
            others = _requested_by_product(sale, exclude_item_id=item.id).get(product.id, 0)
            if others + quantity > product.current_quantity():
                raise InsufficientStockError(
                    f"الكمية المتاحة من {product.name} هي {product.current_quantity()} فقط "
                    f"(مطلوب في الفاتورة: {others + quantity})"
                )
        item.quantity = quantity

    if unit_price is not None:
        if unit_price < 0:
            raise ValueError("السعر لا يمكن أن يكون سالباً")
        if unit_price != item.unit_price and unit_price != product.sale_price and not is_manager:
            raise DiscountLimitExceededError("تغيير السعر يحتاج موافقة المدير")
        item.unit_price = unit_price

    if discount is not None:
        if discount < 0:
            raise ValueError("الخصم لا يمكن أن يكون سالباً")
        gross = item.unit_price * item.quantity
        if discount > gross:
            raise ValueError("الخصم لا يمكن أن يتجاوز قيمة البند")
        if discount > 0 and not is_manager:
            allowed = percent_of(gross, _get_cashier_discount_limit(session) * 100)
            if discount > allowed:
                raise DiscountLimitExceededError(
                    "نسبة الخصم تجاوزت الحد المسموح للكاشير. مطلوب موافقة المدير."
                )
        item.discount = discount

    item.line_total = item.unit_price * item.quantity - item.discount
    session.flush()
    _recalculate_sale_totals(sale)
    return item


def search_sales(
    session: Session,
    user: User,
    date_from: Optional[datetime.date] = None,
    date_to: Optional[datetime.date] = None,
    customer_id: Optional[int] = None,
    cashier_id: Optional[int] = None,
    status: Optional[str] = None,
    text: str = "",
    limit: int = 500,
) -> list[Sale]:
    """Invoice history search (local-date range, newest first).

    ``text`` matches invoice number or any IMEI sold on the invoice.
    """
    q = session.query(Sale).filter(Sale.status != "held")
    if user.role.name != ROLE_MANAGER:      # cashiers only see their own invoices
        cashier_id = user.id
    if date_from:
        q = q.filter(Sale.created_at >= clock.day_bounds_utc(date_from)[0])
    if date_to:
        q = q.filter(Sale.created_at <= clock.day_bounds_utc(date_to)[1])
    if customer_id:
        q = q.filter(Sale.customer_id == customer_id)
    if cashier_id:
        q = q.filter(Sale.user_id == cashier_id)
    if status:
        q = q.filter(Sale.status == status)
    text = (text or "").strip()
    if text:
        like = f"%{text}%"
        imei_ids = session.query(SaleItem.sale_id).join(Device, Device.id == SaleItem.device_id).filter(
            (Device.imei1.like(like)) | (Device.imei2.like(like))
        )
        q = q.filter((Sale.invoice_no.like(like)) | (Sale.id.in_(imei_ids)))
    return q.order_by(Sale.id.desc()).limit(limit).all()


def apply_discount(
    session: Session,
    user: User,
    sale: Sale,
    discount_amount: int,
    manager_override: Optional[User] = None,
) -> None:
    """Apply discount to the invoice total."""
    if sale.status != "held":
        raise SaleError("لا يمكن تعديل فاتورة بعد حفظها")

    if discount_amount < 0:
        raise ValueError("قيمة الخصم لا يمكن أن تكون سالبة")

    if discount_amount > sale.subtotal:
        raise ValueError("الخصم لا يمكن أن يتجاوز إجمالي الفاتورة")

    # Check cashier discount limit
    if discount_amount > 0 and user.role.name != ROLE_MANAGER:
        limit_pct = _get_cashier_discount_limit(session)
        # discount % = (discount / subtotal) * 100
        allowed_max = percent_of(sale.subtotal, limit_pct * 100)
        if discount_amount > allowed_max:
            if not manager_override or manager_override.role.name != ROLE_MANAGER:
                raise DiscountLimitExceededError(
                    f"نسبة الخصم تجاوزت الحد المسموح للكاشير ({limit_pct}%). مطلوب موافقة المدير."
                )

    sale.discount = discount_amount
    sale.total = max(0, sale.subtotal - discount_amount)
    session.flush()


def _recalculate_sale_totals(sale: Sale) -> None:
    """Recalculate subtotal and total from items."""
    sale.subtotal = sum(it.line_total for it in sale.items)
    sale.total = max(0, sale.subtotal - sale.discount)


# ── Holds ─────────────────────────────────────────────────────────────────────

def list_held_sales(session: Session) -> list[Sale]:
    """Held invoices that actually contain items (empty drafts are not listed)."""
    has_items = session.query(SaleItem.sale_id).filter(SaleItem.sale_id == Sale.id).exists()
    return (
        session.query(Sale).filter(Sale.status == "held", has_items)
        .order_by(Sale.id.desc()).all()
    )


def discard_empty_draft(session: Session, sale: Sale) -> bool:
    """Delete a held draft that has no lines. Returns True when deleted."""
    if sale.status == "held" and not sale.items:
        session.delete(sale)
        session.flush()
        return True
    return False


def resume_sale(session: Session, sale_id: int) -> Sale:
    """Retrieve an existing held sale draft."""
    sale = session.get(Sale, sale_id)
    if not sale or sale.status != "held":
        raise SaleError("الفاتورة غير موجودة أو معتمدة بالفعل")
    return sale


# ── Post Sale (Atomic Commit) ─────────────────────────────────────────────────

def post_sale(
    session: Session,
    user: User,
    sale: Sale,
    payments: list[dict],
    manager_override: Optional[User] = None,
) -> Sale:
    """Post sale atomically (all or nothing in one DB transaction).

    Validates:
      1. Cashier must have an open shift.
      2. No duplicate or already sold IMEIs.
      3. Stock availability for accessories/cards.
      4. Below min_price permissions.
      5. Payment totals matching sale total (or customer credit limit check).
    Effects:
      - Stock movements created (signed negative).
      - Devices marked as 'sold'.
      - Drawer cash transaction created for cash payments.
      - Customer debt balance updated for credit remainder.
      - Sale status set to 'posted'.
    """
    require_permission(user.permission_codes(), PERM_SALES_CREATE, user.username)

    if sale.status == "posted":
        raise SaleError("الفاتورة معتمدة ومسجلة بالفعل")

    if not sale.items:
        raise SaleError("لا يمكن اعتماد فاتورة فارغة بدون أصناف")

    # 1. Require open shift
    active_shift = shift_service.get_active_shift(session, user.id)
    if not active_shift:
        raise ShiftRequiredError("يجب فتح وردية أولاً قبل إجراء أي مبيعات")
    sale.shift_id = active_shift.id

    # 2. Check each line item (quantities are totalled per product first)
    _lock_and_refresh_stock(session, sale)
    is_stock_manager = user.role.name == ROLE_MANAGER or (
        manager_override is not None and manager_override.role.name == ROLE_MANAGER)
    wanted = _requested_by_product(sale)
    seen_devices: set[int] = set()
    for item in sale.items:
        product = item.product
        if item.quantity <= 0:
            raise SaleError("الكمية يجب أن تكون أكبر من الصفر")

        # IMEI Check
        if product.track_imei:
            if not item.device:
                raise DeviceNotAvailableError(f"الصنف '{product.name}' يتطلب تحديد جهاز IMEI")
            if item.device.id in seen_devices:
                raise DeviceNotAvailableError(f"الجهاز بالسيريال '{item.device.imei1}' مكرر في الفاتورة")
            seen_devices.add(item.device.id)
            if item.device.status != "in_stock":
                raise DeviceNotAvailableError(f"الجهاز بالسيريال '{item.device.imei1}' مباع أو غير متاح بالمخزن")
        else:
            # Accessory/Card stock check against the TOTAL requested for this product
            current_qty = product.current_quantity()
            if wanted[product.id] > current_qty and not is_stock_manager:
                raise InsufficientStockError(
                    f"الرصيد غير كافٍ للصنف '{product.name}'. المتاح بالمخزن: {current_qty}، المطلوب: {wanted[product.id]}. مطلوب موافقة المدير."
                )

        # Min Price Check
        if item.unit_price < product.min_price:
            can_below = has_permission(user.permission_codes(), PERM_SALES_BELOW_MIN_PRICE)
            is_mgr = can_below or (manager_override and has_permission(manager_override.permission_codes(), PERM_SALES_BELOW_MIN_PRICE))
            if not is_mgr:
                raise PriceBelowMinimumError(
                    f"سعر البيع ({piasters_to_input(item.unit_price)} ج.م) أقل من الحد الأدنى للصنف '{product.name}' ({piasters_to_input(product.min_price)} ج.م). مطلوب موافقة المدير."
                )

    # 3. Check Payments & Split Payments
    # Only CASH can be over-tendered (the excess is change). Wallet/bank/card/credit amounts must fit the total.
    cash_tendered = 0
    non_cash = 0
    credit_amount = 0
    rows: list[dict] = []
    for p in payments:
        amount = int(p.get("amount", 0))
        method = p.get("method", "cash")
        if method not in PAYMENT_METHODS:
            raise SaleError(f"طريقة الدفع غير معروفة: {method}")
        if amount < 0:
            raise SaleError("مبلغ الدفع لا يمكن أن يكون سالباً")
        if amount == 0:
            continue
        if method == "cash":
            cash_tendered += amount
        elif method == "credit":
            credit_amount += amount
            rows.append({"method": method, "amount": amount, "wallet_id": p.get("wallet_id")})
        else:
            non_cash += amount
            rows.append({"method": method, "amount": amount, "wallet_id": p.get("wallet_id")})
    if non_cash + credit_amount > sale.total:
        raise SaleError("مبالغ المحفظة/البنك/الآجل تتجاوز إجمالي الفاتورة؛ الباقي النقدي يُرد فقط من النقدية")

    cash_needed = max(0, sale.total - non_cash - credit_amount)
    cash_paid = min(cash_tendered, cash_needed)        # what actually stays in the drawer
    change_given = cash_tendered - cash_paid           # handed back to the customer
    total_paid = cash_paid + non_cash
    if cash_paid > 0:
        rows.insert(0, {"method": "cash", "amount": cash_paid, "wallet_id": None})

    # Clear any previous payment attempts
    for old_p in list(sale.payments):
        session.delete(old_p)
    session.flush()
    for r in rows:
        session.add(SalePayment(sale_id=sale.id, method=r["method"], amount=r["amount"], wallet_id=r["wallet_id"]))
    session.flush()
    session.expire(sale, ["payments"])
    sale.cash_tendered = cash_tendered
    sale.change_given = change_given

    # Check Credit Eligibility
    remaining = sale.total - total_paid
    if remaining > 0 or credit_amount > 0:
        needed_credit = max(remaining, credit_amount)
        customer = sale.customer
        if customer.name == "عميل نقدي":
            raise SaleError("لا يمكن إجراء بيع آجل (شكك) للعميل النقدي الافتراضي. يرجى اختيار أو إضافة عميل مسجل.")

        # Check credit limit
        if customer.credit_limit > 0 and (customer.balance + needed_credit) > customer.credit_limit:
            is_mgr = user.role.name == ROLE_MANAGER or (manager_override and manager_override.role.name == ROLE_MANAGER)
            if not is_mgr:
                raise CreditLimitExceededError(
                    f"تجاوز العميل '{customer.name}' للحد الائتماني ({piasters_to_input(customer.credit_limit)} ج.م). مطلوب موافقة المدير."
                )

    sale.paid = total_paid
    sale.remaining = max(0, sale.total - total_paid)

    # 4. Apply Stock Movements & Device Status changes
    for item in sale.items:
        product = item.product
        if product.track_imei and item.device:
            # Change device status to sold
            item.device.status = "sold"
            item.device.sale_item_id = item.id

            # Create Stock Movement
            mv = StockMovement(
                product_id=product.id,
                device_id=item.device.id,
                type="sale",
                quantity=-1,
                ref_type="sale",
                ref_id=sale.id,
                user_id=user.id,
                note=f"بيع فاتورة #{sale.invoice_no} | IMEI: {item.device.imei1}",
            )
            session.add(mv)

            # Update product stock quantity
            if product.stock:
                product.stock.quantity = session.query(func.count(Device.id)).filter(
                    Device.product_id == product.id, Device.status == "in_stock"
                ).scalar() or 0
        else:
            # Accessory / Card stock deduction
            if product.stock:
                product.stock.quantity -= item.quantity

            mv = StockMovement(
                product_id=product.id,
                type="sale",
                quantity=-item.quantity,
                ref_type="sale",
                ref_id=sale.id,
                user_id=user.id,
                note=f"بيع فاتورة #{sale.invoice_no}",
            )
            session.add(mv)

    # 5. Cash Drawer Transaction
    if cash_paid > 0:
        drawer = session.query(CashAccount).filter_by(type="drawer").first()
        if drawer:
            drawer.balance += cash_paid
            session.add(CashTransaction(
                account_id=drawer.id,
                type="in",
                amount=cash_paid,
                category="sale",
                ref_type="sale",
                ref_id=sale.id,
                shift_id=sale.shift_id,
                user_id=user.id,
                note=f"متحصلات بيع فاتورة #{sale.invoice_no}",
            ))

    # 6. Customer Debt Balance Update
    if sale.remaining > 0:
        sale.customer.balance += sale.remaining

    sale.status = "posted"
    session.flush()

    log_action(session, "post_sale", user_id=user.id,
               table_name="sales", record_id=sale.id,
               new_value={
                   "invoice_no": sale.invoice_no,
                   "total": sale.total,
                   "paid": sale.paid,
                   "remaining": sale.remaining,
                   "profit": sale.total_profit,
               })
    return sale


# ── Returns & Void ────────────────────────────────────────────────────────────

def return_sale_items(
    session: Session,
    user: User,
    sale_id: int,
    return_items_data: list[dict],
    reason: str,
    restock: bool = True,
    refund_method: str = "cash",
) -> SaleReturn:
    """Return specific items from a posted sale with stock & cash reversals."""
    require_permission(user.permission_codes(), PERM_SALES_RETURN, user.username)

    sale = session.get(Sale, sale_id)
    if not sale or sale.status != "posted":
        raise SaleError("لا يمكن إجراء مرتجع إلا لفاتورة معتمدة")

    if not reason.strip():
        raise ValueError("سبب المرتجع مطلوب")
    if refund_method not in REFUND_METHODS:
        raise SaleError(f"طريقة رد المبلغ غير مقبولة: {refund_method}")

    # ── 1. Validate EVERYTHING before touching any data ──────────────────────
    if not return_items_data:
        raise SaleError("لا توجد أصناف في المرتجع")
    requested: dict[int, int] = {}
    for item_data in return_items_data:
        try:
            qty = int(item_data.get("quantity", 1))
            sid = int(item_data["sale_item_id"])
        except (KeyError, TypeError, ValueError):
            raise SaleError("بيانات المرتجع غير صحيحة")
        if qty <= 0:
            raise SaleError("كمية المرتجع يجب أن تكون أكبر من الصفر")
        requested[sid] = requested.get(sid, 0) + qty          # the same line twice = one total

    plan: list[tuple[SaleItem, int, int]] = []                 # (item, qty, refund)
    for sid, qty in requested.items():
        sale_item = session.get(SaleItem, sid)
        if not sale_item or sale_item.sale_id != sale.id:
            raise SaleError("بند الفاتورة غير صحيح")
        already = session.query(func.coalesce(func.sum(SaleReturnItem.quantity), 0)).filter(
            SaleReturnItem.sale_item_id == sale_item.id
        ).scalar() or 0
        if already + qty > sale_item.quantity:
            raise SaleError(f"الكمية المرتجعة تتجاوز الكمية المباعة للصنف '{sale_item.product.name}'")
        if restock and sale_item.product.track_imei and sale_item.device is not None \
                and sale_item.device.status != "sold":
            raise SaleError(f"الجهاز بالسيريال '{sale_item.device.imei1}' ليس بحالة مباع ولا يمكن إرجاعه للمخزن")
        # Proportional refund that sums exactly to line_total once the whole line is returned
        refund = (sale_item.line_total * (already + qty)) // sale_item.quantity \
            - (sale_item.line_total * already) // sale_item.quantity
        plan.append((sale_item, qty, refund))

    total_refund = sum(r for _, _, r in plan)
    # The refund leaves the drawer under the user's own open shift, else under the shop's open shift
    # (e.g. a manager voiding a cashier's invoice), so the shift's expected cash stays right.
    active_shift = shift_service.get_open_shift_for(session, user)

    # Part of the refund cancels what the customer still owes on this sale; the rest goes back as cash.
    returned_before = session.query(func.coalesce(func.sum(SaleReturn.refund_amount), 0)).filter(
        SaleReturn.sale_id == sale.id).scalar() or 0
    unpaid_at_sale = max(0, sale.total - sale.paid)          # fixed at posting; sale.remaining is derived from it
    debt_part = max(0, min(unpaid_at_sale, returned_before + total_refund) - min(unpaid_at_sale, returned_before))
    debt_reduction = min(debt_part, max(0, sale.customer.balance))
    refund_due = total_refund - debt_reduction
    # Money goes back the way it came: the drawer can only return the CASH that was really received on this
    # sale (and not yet returned); the rest was paid by wallet/bank/card and is refunded there (recorded, no drawer entry).
    cash_refund_due = 0
    if refund_method == "cash" and refund_due > 0:
        cash_received = sum(p.amount for p in sale.payments if p.method == "cash")
        prior_return_ids = [rid for (rid,) in session.query(SaleReturn.id).filter(SaleReturn.sale_id == sale.id)]
        cash_returned = 0
        if prior_return_ids:
            cash_returned = session.query(func.coalesce(func.sum(CashTransaction.amount), 0)).filter(
                CashTransaction.ref_type == "sale_return", CashTransaction.ref_id.in_(prior_return_ids),
                CashTransaction.type == "out").scalar() or 0
        cash_refund_due = min(refund_due, max(0, cash_received - cash_returned))

    # ── 2. Apply ─────────────────────────────────────────────────────────────
    return_no = _generate_return_no(session)
    return_record = SaleReturn(
        sale_id=sale.id,
        return_no=return_no,
        reason=reason,
        refund_amount=total_refund,
        refund_method=refund_method,
        restock=restock,
        user_id=user.id,
    )
    session.add(return_record)
    session.flush()

    for sale_item, qty_to_return, _refund in plan:
        session.add(SaleReturnItem(return_id=return_record.id, sale_item_id=sale_item.id, quantity=qty_to_return))
        if restock:
            product = sale_item.product
            if product.track_imei and sale_item.device:
                sale_item.device.status = "in_stock"
                session.add(StockMovement(
                    product_id=product.id,
                    device_id=sale_item.device.id,
                    type="return_in",
                    quantity=1,
                    ref_type="sale_return",
                    ref_id=return_record.id,
                    user_id=user.id,
                    note=f"مرتجع مبيعات إشعار #{return_no} | IMEI: {sale_item.device.imei1}",
                ))
                if product.stock:
                    product.stock.quantity = session.query(func.count(Device.id)).filter(
                        Device.product_id == product.id, Device.status == "in_stock"
                    ).scalar() or 0
            else:
                if product.stock:
                    product.stock.quantity += qty_to_return
                session.add(StockMovement(
                    product_id=product.id,
                    type="return_in",
                    quantity=qty_to_return,
                    ref_type="sale_return",
                    ref_id=return_record.id,
                    user_id=user.id,
                    note=f"مرتجع مبيعات إشعار #{return_no}",
                ))

    session.expire(sale, ["returns"])        # the collection is reloaded on next access (new return added by id)
    if debt_reduction > 0:
        sale.customer.balance -= debt_reduction
    # what the customer still owes on this invoice after the returns (never below zero)
    sale.remaining = max(0, unpaid_at_sale - min(unpaid_at_sale, returned_before + total_refund))

    if cash_refund_due > 0 and refund_method == "cash":
        drawer = session.query(CashAccount).filter_by(type="drawer").first()
        if drawer:
            drawer.balance -= cash_refund_due
            session.add(CashTransaction(
                account_id=drawer.id,
                type="out",
                amount=cash_refund_due,
                category="return",
                ref_type="sale_return",
                ref_id=return_record.id,
                shift_id=active_shift.id if active_shift else None,
                user_id=user.id,
                note=f"صرف قيمة مرتجع مبيعات إشعار #{return_no}",
            ))

    session.flush()
    log_action(session, "return_sale_items", user_id=user.id,
               table_name="sale_returns", record_id=return_record.id,
               new_value={"return_no": return_no, "refund_amount": total_refund, "cash_refunded": cash_refund_due,
                          "debt_cancelled": debt_reduction, "reason": reason})
    return return_record


def void_sale(session: Session, user: User, sale_id: int, reason: str) -> Sale:
    """Void an entire posted sale (Manager only). Implemented as full return + void status."""
    require_permission(user.permission_codes(), PERM_SALES_VOID, user.username)

    sale = session.get(Sale, sale_id)
    if not sale or sale.status != "posted":
        raise SaleError("لا يمكن إلغاء إلا فاتورة معتمدة")

    if not reason.strip():
        raise ValueError("سبب الإلغاء مطلوب")

    # Return whatever has not been returned yet (a partly returned sale can still be voided)
    items_to_return = []
    for it in sale.items:
        done = session.query(func.coalesce(func.sum(SaleReturnItem.quantity), 0)).filter(
            SaleReturnItem.sale_item_id == it.id).scalar() or 0
        if it.quantity - done > 0:
            items_to_return.append({"sale_item_id": it.id, "quantity": it.quantity - done})
    if items_to_return:
        return_sale_items(
            session, user, sale.id, items_to_return,
            reason=f"إلغاء كامل للفاتورة: {reason}",
            restock=True,
            refund_method="cash",
        )

    sale.status = "void"
    session.flush()

    log_action(session, "void_sale", user_id=user.id,
               table_name="sales", record_id=sale.id,
               new_value={"reason": reason})
    return sale


# ── Warranty Search ───────────────────────────────────────────────────────────

def search_warranty(session: Session, query: str) -> list[dict]:
    """Search warranty by IMEI, invoice_no, or customer phone."""
    query = query.strip()
    if not query:
        return []

    # Search by device IMEI
    device = session.query(Device).filter(
        (Device.imei1 == query) | (Device.imei2 == query)
    ).first()

    results = []
    if device and device.sale_item_id:
        sale_item = session.get(SaleItem, device.sale_item_id)
        if sale_item:
            results.append(_format_warranty_info(sale_item, device))

    # Search by Invoice No
    sales = session.query(Sale).filter(Sale.invoice_no.ilike(f"%{query}%")).all()
    for s in sales:
        for it in s.items:
            results.append(_format_warranty_info(it, it.device))

    # Search by Customer Phone
    customers = session.query(Customer).filter(Customer.phone.ilike(f"%{query}%")).all()
    for c in customers:
        for s in c.sales:
            if s.status == "posted":
                for it in s.items:
                    results.append(_format_warranty_info(it, it.device))

    # Deduplicate by sale_item_id
    seen = set()
    deduped = []
    for r in results:
        if r["sale_item_id"] not in seen:
            seen.add(r["sale_item_id"])
            deduped.append(r)
    return deduped


def _format_warranty_info(item: SaleItem, device: Optional[Device]) -> dict:
    now = utcnow()
    is_valid = item.warranty_end_date is not None and item.warranty_end_date >= now
    days_left = (item.warranty_end_date - now).days if (item.warranty_end_date and is_valid) else 0

    return {
        "sale_item_id": item.id,
        "invoice_no": item.sale.invoice_no,
        "sale_date": item.sale.created_at,
        "customer_name": item.sale.customer.name if item.sale.customer else "—",
        "customer_phone": (item.sale.customer.phone if item.sale.customer else "") or "",
        "product_name": item.product.name,
        "imei": device.imei1 if device else "—",
        "warranty_days": item.product.warranty_days,
        "warranty_end_date": item.warranty_end_date,
        "is_valid": is_valid,
        "days_left": days_left,
    }
