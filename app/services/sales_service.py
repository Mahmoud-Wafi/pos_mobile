"""Sales service — POS operations, invoice posting, atomic transactions, returns, and warranty."""
from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.money import percent_of
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_invoice_no(session: Session) -> str:
    """Generate sequential invoice number: INV-YYYYMMDD-####."""
    today_str = datetime.datetime.utcnow().strftime("%Y%m%d")
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
    today_str = datetime.datetime.utcnow().strftime("%Y%m%d")
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
        unit_cost = device.total_cost
        quantity = 1  # Each phone line is 1 device
    else:
        unit_cost = product.cost_price

    # Calculate warranty end date
    warranty_end = None
    if product.warranty_days > 0:
        warranty_end = datetime.datetime.utcnow() + datetime.timedelta(days=product.warranty_days)

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
    if sale.status != "held":
        raise SaleError("لا يمكن تعديل فاتورة بعد حفظها")

    item = session.get(SaleItem, item_id)
    if item and item.sale_id == sale.id:
        session.delete(item)
        session.flush()
        _recalculate_sale_totals(sale)


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
    """List all currently held sales drafts."""
    return session.query(Sale).filter_by(status="held").order_by(Sale.id.desc()).all()


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

    # 2. Check each line item
    for item in sale.items:
        product = item.product

        # IMEI Check
        if product.track_imei:
            if not item.device:
                raise DeviceNotAvailableError(f"الصنف '{product.name}' يتطلب تحديد جهاز IMEI")
            if item.device.status != "in_stock":
                raise DeviceNotAvailableError(f"الجهاز بالسيريال '{item.device.imei1}' مباع أو غير متاح بالمخزن")
        else:
            # Accessory/Card Stock check
            current_qty = product.current_quantity()
            if item.quantity > current_qty:
                is_mgr = user.role.name == ROLE_MANAGER or (manager_override and manager_override.role.name == ROLE_MANAGER)
                if not is_mgr:
                    raise InsufficientStockError(
                        f"الرصيد غير كافٍ للصنف '{product.name}'. المتاح بالمخزن: {current_qty}، المطلوب: {item.quantity}. مطلوب موافقة المدير."
                    )

        # Min Price Check
        if item.unit_price < product.min_price:
            can_below = has_permission(user.permission_codes(), PERM_SALES_BELOW_MIN_PRICE)
            is_mgr = can_below or (manager_override and has_permission(manager_override.permission_codes(), PERM_SALES_BELOW_MIN_PRICE))
            if not is_mgr:
                raise PriceBelowMinimumError(
                    f"سعر البيع ({item.unit_price / 100} ج.م) أقل من الحد الأدنى للصنف '{product.name}' ({product.min_price / 100} ج.م). مطلوب موافقة المدير."
                )

    # 3. Check Payments & Split Payments
    total_paid = 0
    cash_paid = 0
    credit_amount = 0

    # Clear any previous payment attempts
    for p in list(sale.payments):
        session.delete(p)

    for p in payments:
        amount = int(p.get("amount", 0))
        method = p.get("method", "cash")
        wallet_id = p.get("wallet_id")
        if amount <= 0:
            continue

        if method == "credit":
            credit_amount += amount
        else:
            total_paid += amount
            if method == "cash":
                cash_paid += amount

        sp = SalePayment(
            sale_id=sale.id,
            method=method,
            amount=amount,
            wallet_id=wallet_id,
        )
        session.add(sp)

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
                    f"تجاوز العميل '{customer.name}' للحد الائتماني ({customer.credit_limit / 100} ج.م). مطلوب موافقة المدير."
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

    return_no = _generate_return_no(session)
    total_refund = 0

    return_record = SaleReturn(
        sale_id=sale.id,
        return_no=return_no,
        reason=reason,
        refund_amount=0,
        refund_method=refund_method,
        restock=restock,
        user_id=user.id,
    )
    session.add(return_record)
    session.flush()

    for item_data in return_items_data:
        sale_item_id = item_data["sale_item_id"]
        qty_to_return = int(item_data.get("quantity", 1))

        sale_item = session.get(SaleItem, sale_item_id)
        if not sale_item or sale_item.sale_id != sale.id:
            raise SaleError("بند الفاتورة غير صحيح")

        # Check previously returned qty
        already_returned = session.query(func.coalesce(func.sum(SaleReturnItem.quantity), 0)).filter(
            SaleReturnItem.sale_item_id == sale_item.id
        ).scalar() or 0

        if (already_returned + qty_to_return) > sale_item.quantity:
            raise SaleError(f"الكمية المرتجعة تتجاوز الكمية المباعة للصنف '{sale_item.product.name}'")

        # Calculate refund for this item
        unit_effective_price = sale_item.line_total // sale_item.quantity
        line_refund = unit_effective_price * qty_to_return
        total_refund += line_refund

        session.add(SaleReturnItem(
            return_id=return_record.id,
            sale_item_id=sale_item.id,
            quantity=qty_to_return,
        ))

        # Restock logic
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

    return_record.refund_amount = total_refund

    # Reversal of money / debt
    if sale.customer.balance > 0 and sale.remaining > 0:
        # If customer had debt on this sale, reverse debt first
        debt_reduction = min(sale.customer.balance, total_refund)
        sale.customer.balance -= debt_reduction
        cash_refund_due = total_refund - debt_reduction
    else:
        cash_refund_due = total_refund

    # If cash refund leaves the drawer
    if cash_refund_due > 0 and refund_method == "cash":
        drawer = session.query(CashAccount).filter_by(type="drawer").first()
        if drawer:
            drawer.balance -= cash_refund_due
            active_shift = shift_service.get_active_shift(session, user.id)
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
               new_value={"return_no": return_no, "refund_amount": total_refund, "reason": reason})
    return return_record


def void_sale(session: Session, user: User, sale_id: int, reason: str) -> Sale:
    """Void an entire posted sale (Manager only). Implemented as full return + void status."""
    require_permission(user.permission_codes(), PERM_SALES_VOID, user.username)

    sale = session.get(Sale, sale_id)
    if not sale or sale.status != "posted":
        raise SaleError("لا يمكن إلغاء إلا فاتورة معتمدة")

    if not reason.strip():
        raise ValueError("سبب الإلغاء مطلوب")

    # Full return of all items
    items_to_return = [{"sale_item_id": it.id, "quantity": it.quantity} for it in sale.items]
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
    now = datetime.datetime.utcnow()
    is_valid = item.warranty_end_date is not None and item.warranty_end_date >= now
    days_left = (item.warranty_end_date - now).days if (item.warranty_end_date and is_valid) else 0

    return {
        "sale_item_id": item.id,
        "invoice_no": item.sale.invoice_no,
        "sale_date": item.sale.created_at,
        "customer_name": item.sale.customer.name,
        "customer_phone": item.sale.customer.phone or "",
        "product_name": item.product.name,
        "imei": device.imei1 if device else "—",
        "warranty_days": item.product.warranty_days,
        "warranty_end_date": item.warranty_end_date,
        "is_valid": is_valid,
        "days_left": days_left,
    }
