"""Purchase service — handles supplier invoices, payments, weighted-average costing,
and used-device purchases with legal declarations.
"""
from __future__ import annotations

import datetime
from app.core.clock import utcnow
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.money import weighted_average_cost
from app.core.permissions import (
    PERM_PURCHASES_CREATE,
    PERM_PURCHASES_VIEW,
    require_permission,
)
from app.models.accounting import CashAccount, CashTransaction
from app.models.product import Product
from app.models.purchase import (
    Purchase,
    PurchaseItem,
    Supplier,
    SupplierPayment,
    UsedDevicePurchase,
)
from app.models.stock import Device, Stock, StockMovement
from app.models.user import User
from app.printing.declaration import generate_used_device_declaration_pdf


class PurchaseError(Exception):
    """Base exception for purchase operations."""
    pass


class SupplierNotFound(PurchaseError):
    pass


class DuplicateSupplierName(PurchaseError):
    pass


class DuplicateInvoiceNumber(PurchaseError):
    pass


class InvalidPurchaseItem(PurchaseError):
    pass


class DuplicateIMEIError(PurchaseError):
    pass


def _get_default_cash_account(session: Session, account_id: Optional[int] = None) -> CashAccount:
    """Return requested cash account or the main cash drawer."""
    if account_id:
        acc = session.get(CashAccount, account_id)
        if acc:
            return acc
    drawer = session.query(CashAccount).filter(CashAccount.type == "drawer").first()
    if not drawer:
        drawer = CashAccount(name="الدرج الرئيسي", type="drawer", balance=0)
        session.add(drawer)
        session.flush()
    return drawer


def _ensure_stock_row(session: Session, product: Product) -> Stock:
    stock = session.query(Stock).filter(Stock.product_id == product.id).first()
    if stock is None:
        stock = Stock(product_id=product.id, quantity=0)
        session.add(stock)
        session.flush()
    return stock


def _sync_device_count(session: Session, product: Product) -> None:
    stock = _ensure_stock_row(session, product)
    count = (
        session.query(func.count(Device.id))
        .filter(Device.product_id == product.id, Device.status == "in_stock")
        .scalar()
        or 0
    )
    stock.quantity = count


# ── Supplier Operations ────────────────────────────────────────────────────────

def create_supplier(
    session: Session,
    user: User,
    name: str,
    phone: Optional[str] = None,
    notes: Optional[str] = None,
    initial_balance: int = 0,
) -> Supplier:
    """Create a new supplier."""
    require_permission(user.permission_codes(), PERM_PURCHASES_CREATE, user.username)
    clean_name = name.strip()
    if not clean_name:
        raise PurchaseError("اسم المورد مطلوب")

    existing = session.query(Supplier).filter(Supplier.name == clean_name).first()
    if existing:
        raise DuplicateSupplierName(f"المورد '{clean_name}' مسجل مسبقاً")

    supplier = Supplier(
        name=clean_name,
        phone=phone.strip() if phone else None,
        notes=notes.strip() if notes else None,
        balance=initial_balance,
    )
    session.add(supplier)
    session.flush()

    log_action(
        session,
        "create_supplier",
        user_id=user.id,
        table_name="suppliers",
        record_id=supplier.id,
        new_value={"name": supplier.name, "phone": supplier.phone, "balance": supplier.balance},
    )
    return supplier


def update_supplier(
    session: Session,
    user: User,
    supplier_id: int,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    notes: Optional[str] = None,
) -> Supplier:
    """Update supplier profile information."""
    require_permission(user.permission_codes(), PERM_PURCHASES_CREATE, user.username)
    supplier = session.get(Supplier, supplier_id)
    if not supplier:
        raise SupplierNotFound(f"المورد رقم {supplier_id} غير موجود")

    old_val = {"name": supplier.name, "phone": supplier.phone, "notes": supplier.notes}

    if name is not None:
        clean_name = name.strip()
        if clean_name != supplier.name:
            dup = session.query(Supplier).filter(Supplier.name == clean_name, Supplier.id != supplier_id).first()
            if dup:
                raise DuplicateSupplierName(f"المورد '{clean_name}' مسجل مسبقاً")
            supplier.name = clean_name
    if phone is not None:
        supplier.phone = phone.strip() if phone else None
    if notes is not None:
        supplier.notes = notes.strip() if notes else None

    log_action(
        session,
        "update_supplier",
        user_id=user.id,
        table_name="suppliers",
        record_id=supplier.id,
        old_value=old_val,
        new_value={"name": supplier.name, "phone": supplier.phone, "notes": supplier.notes},
    )
    session.flush()
    return supplier


def get_supplier(session: Session, user: User, supplier_id: int) -> Supplier:
    require_permission(user.permission_codes(), PERM_PURCHASES_VIEW, user.username)
    supplier = session.get(Supplier, supplier_id)
    if not supplier:
        raise SupplierNotFound(f"المورد رقم {supplier_id} غير موجود")
    return supplier


def list_suppliers(
    session: Session,
    user: User,
    search: Optional[str] = None,
) -> list[Supplier]:
    require_permission(user.permission_codes(), PERM_PURCHASES_VIEW, user.username)
    q = session.query(Supplier)
    if search:
        s = f"%{search.strip()}%"
        q = q.filter(or_(Supplier.name.ilike(s), Supplier.phone.ilike(s)))
    return q.order_by(Supplier.name.asc()).all()


# ── Purchase Invoices ─────────────────────────────────────────────────────────

def create_purchase(
    session: Session,
    user: User,
    supplier_id: int,
    invoice_number: str,
    items_data: list[dict[str, Any]],
    paid_amount: int = 0,
    account_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> Purchase:
    """Create and post a purchase invoice atomically.

    items_data: list of dicts:
      - product_id: int
      - quantity: int
      - unit_cost: int (piasters)
      - imeis: list[dict] with 'imei1', optional 'imei2' (mandatory for track_imei products)
    """
    require_permission(user.permission_codes(), PERM_PURCHASES_CREATE, user.username)

    supplier = session.get(Supplier, supplier_id)
    if not supplier:
        raise SupplierNotFound(f"المورد رقم {supplier_id} غير موجود")

    clean_invoice_no = invoice_number.strip()
    if not clean_invoice_no:
        raise PurchaseError("رقم فاتورة الشراء مطلوب")

    existing_inv = session.query(Purchase).filter(Purchase.invoice_number == clean_invoice_no).first()
    if existing_inv:
        raise DuplicateInvoiceNumber(f"فاتورة الشراء '{clean_invoice_no}' مسجلة مسبقاً")

    if not items_data:
        raise PurchaseError("لا يمكن حفظ فاتورة شراء بدون أصناف")

    # Build Purchase object
    purchase = Purchase(
        invoice_number=clean_invoice_no,
        supplier_id=supplier.id,
        total=0,
        paid=0,
        balance=0,
        status="posted",
        notes=notes.strip() if notes else None,
        user_id=user.id,
        created_at=utcnow(),
    )
    session.add(purchase)
    session.flush()

    total_invoice_piasters = 0
    seen_imeis: set[str] = set()

    for item_data in items_data:
        product_id = item_data.get("product_id")
        product = session.get(Product, product_id)
        if not product:
            raise InvalidPurchaseItem(f"المنتج رقم {product_id} غير موجود")

        qty = int(item_data.get("quantity", 0))
        if qty <= 0:
            raise InvalidPurchaseItem(f"الكمية غير صحيحة للصنف {product.name}")

        unit_cost = int(item_data.get("unit_cost", 0))
        if unit_cost < 0:
            raise InvalidPurchaseItem(f"سعر التكلفة غير صحيح للصنف {product.name}")

        line_total = qty * unit_cost
        total_invoice_piasters += line_total

        p_item = PurchaseItem(
            purchase_id=purchase.id,
            product_id=product.id,
            quantity=qty,
            unit_cost=unit_cost,
            total=line_total,
        )
        session.add(p_item)
        purchase.items.append(p_item)

        # Handle Phones (IMEI Tracking)
        if product.track_imei:
            imeis = item_data.get("imeis") or []
            if len(imeis) != qty:
                raise InvalidPurchaseItem(
                    f"المنتج '{product.name}' يتطلب إدخال {qty} سيريال (IMEI)، تم إدخال {len(imeis)}"
                )

            for imei_entry in imeis:
                imei1 = str(imei_entry.get("imei1", "")).strip()
                imei2 = str(imei_entry.get("imei2", "")).strip() if imei_entry.get("imei2") else None

                if not imei1:
                    raise InvalidPurchaseItem(f"رقم IMEI فارغ للمنتج {product.name}")

                if imei1 in seen_imeis:
                    raise DuplicateIMEIError(f"تكرار رقم IMEI في نفس الفاتورة: {imei1}")
                seen_imeis.add(imei1)

                # Check unique against DB
                dup = session.query(Device).filter(or_(Device.imei1 == imei1, Device.imei2 == imei1)).first()
                if dup:
                    raise DuplicateIMEIError(f"رقم IMEI '{imei1}' مسجل بالفعل في النظام")

                if imei2:
                    if imei2 in seen_imeis:
                        raise DuplicateIMEIError(f"تكرار رقم IMEI الثاني في نفس الفاتورة: {imei2}")
                    seen_imeis.add(imei2)
                    dup2 = session.query(Device).filter(or_(Device.imei1 == imei2, Device.imei2 == imei2)).first()
                    if dup2:
                        raise DuplicateIMEIError(f"رقم IMEI الثاني '{imei2}' مسجل بالفعل في النظام")

                device = Device(
                    product_id=product.id,
                    imei1=imei1,
                    imei2=imei2,
                    condition="new",
                    purchase_cost=unit_cost,
                    extra_cost=0,
                    status="in_stock",
                    purchase_id=purchase.id,
                    created_by=user.id,
                )
                session.add(device)
                session.flush()

                # Add stock movement for phone
                mov = StockMovement(
                    product_id=product.id,
                    type="purchase",
                    quantity=1,
                    device_id=device.id,
                    ref_type="purchase",
                    ref_id=purchase.id,
                    note=f"فاتورة شراء {purchase.invoice_number} (IMEI: {imei1})",
                    user_id=user.id,
                )
                session.add(mov)

            _sync_device_count(session, product)

        else:
            # Handle Accessories / Cards (Weighted Average Cost Update)
            stock = _ensure_stock_row(session, product)
            old_qty = stock.quantity
            old_avg = product.cost_price

            new_avg = weighted_average_cost(old_qty, old_avg, qty, unit_cost)
            product.cost_price = new_avg
            stock.quantity += qty

            mov = StockMovement(
                product_id=product.id,
                type="purchase",
                quantity=qty,
                ref_type="purchase",
                ref_id=purchase.id,
                note=f"فاتورة شراء {purchase.invoice_number}",
                user_id=user.id,
            )
            session.add(mov)

    # Set totals
    purchase.total = total_invoice_piasters

    if paid_amount < 0:
        raise PurchaseError("المبلغ المدفوع لا يمكن أن يكون سالباً")
    if paid_amount > total_invoice_piasters:
        raise PurchaseError("المبلغ المدفوع أكبر من إجمالي الفاتورة")

    purchase.paid = paid_amount
    purchase.balance = total_invoice_piasters - paid_amount

    # Update supplier balance (+ unpaid amount)
    # Supplier balance represents what shop owes supplier (purchases - payments)
    supplier.balance += purchase.balance

    # Record Payment if paid_amount > 0
    if paid_amount > 0:
        cash_acc = _get_default_cash_account(session, account_id)
        cash_acc.balance -= paid_amount

        cash_tx = CashTransaction(
            account_id=cash_acc.id,
            type="out",
            amount=paid_amount,
            category="purchase",
            ref_type="purchase",
            ref_id=purchase.id,
            user_id=user.id,
            note=f"دفعة نقدية لفاتورة الشراء {purchase.invoice_number}",
        )
        session.add(cash_tx)
        session.flush()

        payment = SupplierPayment(
            supplier_id=supplier.id,
            purchase_id=purchase.id,
            amount=paid_amount,
            method="cash",
            account_id=cash_acc.id,
            cash_transaction_id=cash_tx.id,
            user_id=user.id,
            note=f"سداد دفعة فورية مع الفاتورة {purchase.invoice_number}",
        )
        session.add(payment)
        purchase.payments.append(payment)

    log_action(
        session,
        "create_purchase",
        user_id=user.id,
        table_name="purchases",
        record_id=purchase.id,
        new_value={
            "invoice_number": purchase.invoice_number,
            "supplier_id": supplier.id,
            "total": purchase.total,
            "paid": purchase.paid,
            "balance": purchase.balance,
            "items_count": len(items_data),
        },
    )
    session.flush()
    return purchase


def pay_supplier(
    session: Session,
    user: User,
    supplier_id: int,
    amount: int,
    account_id: Optional[int] = None,
    method: str = "cash",
    note: Optional[str] = None,
    purchase_id: Optional[int] = None,
) -> SupplierPayment:
    """Record a debt payment made to a supplier."""
    require_permission(user.permission_codes(), PERM_PURCHASES_CREATE, user.username)

    if amount <= 0:
        raise PurchaseError("مبلغ السداد يجب أن يكون أكبر من الصفر")

    supplier = session.get(Supplier, supplier_id)
    if not supplier:
        raise SupplierNotFound(f"المورد رقم {supplier_id} غير موجود")

    cash_acc = _get_default_cash_account(session, account_id)
    cash_acc.balance -= amount

    cash_tx = CashTransaction(
        account_id=cash_acc.id,
        type="out",
        amount=amount,
        category="supplier_payment",
        ref_type="supplier_payment",
        ref_id=supplier.id,
        user_id=user.id,
        note=f"سداد للمورد: {supplier.name} - {note or ''}".strip(),
    )
    session.add(cash_tx)
    session.flush()

    # Decrease supplier balance (we owe them less)
    supplier.balance -= amount

    payment = SupplierPayment(
        supplier_id=supplier.id,
        purchase_id=purchase_id,
        amount=amount,
        method=method,
        account_id=cash_acc.id,
        cash_transaction_id=cash_tx.id,
        user_id=user.id,
        note=note.strip() if note else None,
    )
    session.add(payment)
    session.flush()

    log_action(
        session,
        "pay_supplier",
        user_id=user.id,
        table_name="supplier_payments",
        record_id=payment.id,
        new_value={
            "supplier_id": supplier.id,
            "amount": amount,
            "new_supplier_balance": supplier.balance,
        },
    )
    return payment


# ── Used Device Purchases ─────────────────────────────────────────────────────

def record_used_device_purchase(
    session: Session,
    user: User,
    seller_name: str,
    seller_national_id: str,
    seller_phone: str,
    product_id: int,
    imei1: str,
    price: int,
    condition_notes: Optional[str] = None,
    imei2: Optional[str] = None,
    account_id: Optional[int] = None,
) -> UsedDevicePurchase:
    """Buy a used phone from an individual seller.

    Validates seller credentials, adds device to inventory with condition='used',
    deducts cash from drawer, and creates UsedDevicePurchase record.
    """
    require_permission(user.permission_codes(), PERM_PURCHASES_CREATE, user.username)

    clean_seller_name = seller_name.strip()
    if not clean_seller_name:
        raise PurchaseError("اسم البائع الرباعي مطلوب")

    clean_nid = seller_national_id.strip()
    if len(clean_nid) != 14 or not clean_nid.isdigit():
        raise PurchaseError("الرقم القومي للبائع يجب أن يتكون من 14 رقماً صحيحاً")

    clean_phone = seller_phone.strip()
    if not clean_phone:
        raise PurchaseError("رقم هاتف البائع مطلوب")

    if price <= 0:
        raise PurchaseError("سعر الشراء يجب أن يكون أكبر من الصفر")

    product = session.get(Product, product_id)
    if not product:
        raise PurchaseError("المنتج المحدد غير موجود")
    if not product.track_imei:
        raise PurchaseError("الأجهزة المستعملة تتطلب منتج هاتف يتبع بـ IMEI")

    clean_imei1 = imei1.strip()
    if not clean_imei1:
        raise PurchaseError("رقم IMEI الأول مطلوب")

    # Check uniqueness
    dup1 = session.query(Device).filter(or_(Device.imei1 == clean_imei1, Device.imei2 == clean_imei1)).first()
    if dup1:
        raise DuplicateIMEIError(f"رقم IMEI '{clean_imei1}' مسجل بالفعل بالنظام")

    clean_imei2 = imei2.strip() if imei2 else None
    if clean_imei2:
        dup2 = session.query(Device).filter(or_(Device.imei1 == clean_imei2, Device.imei2 == clean_imei2)).first()
        if dup2:
            raise DuplicateIMEIError(f"رقم IMEI الثاني '{clean_imei2}' مسجل بالفعل بالنظام")

    # Create physical device with condition = 'used'
    device = Device(
        product_id=product.id,
        imei1=clean_imei1,
        imei2=clean_imei2,
        condition="used",
        purchase_cost=price,
        extra_cost=0,
        status="in_stock",
        notes=f"Used device purchased from {clean_seller_name} (NID: {clean_nid})",
        created_by=user.id,
    )
    session.add(device)
    session.flush()

    # Movement
    mov = StockMovement(
        product_id=product.id,
        type="purchase",
        quantity=1,
        device_id=device.id,
        ref_type="used_device",
        note=f"شراء جهاز مستعمل من {clean_seller_name}",
        user_id=user.id,
    )
    session.add(mov)

    _sync_device_count(session, product)

    # Drawer Cash Out
    cash_acc = _get_default_cash_account(session, account_id)
    cash_acc.balance -= price

    cash_tx = CashTransaction(
        account_id=cash_acc.id,
        type="out",
        amount=price,
        category="used_device_purchase",
        ref_type="used_device_purchase",
        ref_id=device.id,
        user_id=user.id,
        note=f"شراء هاتف مستعمل {product.name} (IMEI: {clean_imei1}) من {clean_seller_name}",
    )
    session.add(cash_tx)
    session.flush()

    # Used Device Record
    used_purchase = UsedDevicePurchase(
        seller_name=clean_seller_name,
        seller_national_id=clean_nid,
        seller_phone=clean_phone,
        device_id=device.id,
        price=price,
        condition_notes=condition_notes.strip() if condition_notes else None,
        declaration_printed=False,
        cash_transaction_id=cash_tx.id,
        user_id=user.id,
    )
    session.add(used_purchase)
    session.flush()

    log_action(
        session,
        "record_used_device_purchase",
        user_id=user.id,
        table_name="used_device_purchases",
        record_id=used_purchase.id,
        new_value={
            "seller_name": clean_seller_name,
            "seller_national_id": clean_nid,
            "device_id": device.id,
            "imei1": clean_imei1,
            "price": price,
            "condition": "used",
        },
    )
    return used_purchase


def generate_declaration(
    session: Session,
    user: User,
    used_purchase_id: int,
    dest_path: Optional[Path | str] = None,
    shop_name: str = "محل الموبايلات",
) -> Path:
    """Generate and mark declaration PDF as printed."""
    require_permission(user.permission_codes(), PERM_PURCHASES_VIEW, user.username)
    used_purchase = session.get(UsedDevicePurchase, used_purchase_id)
    if not used_purchase:
        raise PurchaseError(f"سجل شراء الجهاز المستعمل {used_purchase_id} غير موجود")

    if not dest_path:
        dest_path = Path("data/declarations") / f"declaration_{used_purchase.id:05d}.pdf"

    pdf_path = generate_used_device_declaration_pdf(
        used_purchase=used_purchase,
        dest_path=dest_path,
        shop_name=shop_name,
    )
    used_purchase.declaration_printed = True
    session.flush()

    log_action(
        session,
        "print_used_device_declaration",
        user_id=user.id,
        table_name="used_device_purchases",
        record_id=used_purchase.id,
        new_value={"dest_path": str(pdf_path)},
    )
    return pdf_path


def list_purchases(
    session: Session,
    user: User,
    supplier_id: Optional[int] = None,
) -> list[Purchase]:
    require_permission(user.permission_codes(), PERM_PURCHASES_VIEW, user.username)
    q = session.query(Purchase)
    if supplier_id:
        q = q.filter(Purchase.supplier_id == supplier_id)
    return q.order_by(Purchase.created_at.desc()).all()


def list_used_purchases(
    session: Session,
    user: User,
    search: Optional[str] = None,
) -> list[UsedDevicePurchase]:
    require_permission(user.permission_codes(), PERM_PURCHASES_VIEW, user.username)
    q = session.query(UsedDevicePurchase)
    if search:
        s = f"%{search.strip()}%"
        q = q.filter(
            or_(
                UsedDevicePurchase.seller_name.ilike(s),
                UsedDevicePurchase.seller_national_id.ilike(s),
                UsedDevicePurchase.seller_phone.ilike(s),
            )
        )
    return q.order_by(UsedDevicePurchase.created_at.desc()).all()
