"""Customer service — public API for customer management and debt collection."""
from __future__ import annotations

from typing import Optional
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.permissions import (
    PERM_CUSTOMERS_MANAGE, PERM_CUSTOMERS_COLLECT, require_permission,
)
from app.models.customer import Customer, CustomerPayment
from app.models.accounting import CashAccount, CashTransaction
from app.models.user import User


class CustomerNotFound(Exception):
    pass


class InvalidCreditLimit(Exception):
    pass


def get_default_customer(session: Session) -> Customer:
    """Return the default 'عميل نقدي'."""
    cust = session.query(Customer).filter_by(name="عميل نقدي").first()
    if cust is None:
        cust = Customer(name="عميل نقدي", phone="", credit_limit=0, balance=0)
        session.add(cust)
        session.flush()
    return cust


def create_customer(session: Session, user: User, data: dict) -> Customer:
    """Create a new customer account."""
    require_permission(user.permission_codes(), PERM_CUSTOMERS_MANAGE, user.username)

    name = data.get("name", "").strip()
    if not name:
        raise ValueError("اسم العميل مطلوب")

    customer = Customer(
        name=name,
        phone=data.get("phone", "").strip() or None,
        national_id=data.get("national_id", "").strip() or None,
        credit_limit=int(data.get("credit_limit", 0)),
        balance=0,
        notes=data.get("notes"),
        created_by=user.id,
    )
    session.add(customer)
    session.flush()

    log_action(session, "create_customer", user_id=user.id,
               table_name="customers", record_id=customer.id,
               new_value={"name": customer.name, "phone": customer.phone})
    return customer


def update_customer(session: Session, user: User, customer_id: int, data: dict) -> Customer:
    """Update customer details."""
    require_permission(user.permission_codes(), PERM_CUSTOMERS_MANAGE, user.username)
    customer = session.get(Customer, customer_id)
    if not customer:
        raise CustomerNotFound(f"العميل رقم {customer_id} غير موجود")

    for field in ("name", "phone", "national_id", "credit_limit", "notes"):
        if field in data:
            setattr(customer, field, data[field])

    session.flush()
    log_action(session, "update_customer", user_id=user.id,
               table_name="customers", record_id=customer.id,
               new_value=data)
    return customer


def search_customers(session: Session, query: str = "") -> list[Customer]:
    """Search customers by name or phone."""
    q = session.query(Customer)
    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter((Customer.name.ilike(pattern)) | (Customer.phone.ilike(pattern)))
    return q.order_by(Customer.name).all()


def collect_payment(
    session: Session,
    user: User,
    customer_id: int,
    amount_piasters: int,
    method: str = "cash",
    shift_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> CustomerPayment:
    """Collect a debt payment from a customer.

    Reduces customer debt (balance) and increases cash drawer if method is 'cash'.
    """
    require_permission(user.permission_codes(), PERM_CUSTOMERS_COLLECT, user.username)

    if amount_piasters <= 0:
        raise ValueError("مبلغ السداد يجب أن يكون أكبر من الصفر")

    customer = session.get(Customer, customer_id)
    if not customer:
        raise CustomerNotFound(f"العميل رقم {customer_id} غير موجود")

    if customer.name == "عميل نقدي":
        raise ValueError("لا يمكن تسجيل سداد آجل للعميل النقدي الافتراضي")

    # Record CustomerPayment
    payment = CustomerPayment(
        customer_id=customer.id,
        amount=amount_piasters,
        method=method,
        shift_id=shift_id,
        user_id=user.id,
        notes=notes,
    )
    session.add(payment)

    # Reduce customer balance (positive = owes shop)
    customer.balance -= amount_piasters

    # If cash, increase drawer balance
    if method == "cash":
        drawer = session.query(CashAccount).filter_by(type="drawer").first()
        if drawer:
            drawer.balance += amount_piasters
            session.add(CashTransaction(
                account_id=drawer.id,
                type="in",
                amount=amount_piasters,
                category="debt_collection",
                ref_type="customer_payment",
                ref_id=payment.id,
                shift_id=shift_id,
                user_id=user.id,
                note=f"سداد مديونية العميل: {customer.name}",
            ))

    session.flush()
    log_action(session, "collect_payment", user_id=user.id,
               table_name="customer_payments", record_id=payment.id,
               new_value={"customer": customer.name, "amount": amount_piasters, "balance_after": customer.balance})
    return payment

