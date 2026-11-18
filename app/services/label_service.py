"""Build label specs from products / devices (inventory.view) and render them to PDF."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.money import format_money
from app.core.permissions import PERM_INVENTORY_VIEW, require_permission
from app.i18n import ar
from app.models.product import Product
from app.models.stock import Device
from app.models.user import User
from app.printing.labels import LabelSpec, make_labels_pdf

MAX_LABELS = 500


class LabelError(Exception):
    """Business error with an Arabic message."""


def product_code(product: Product) -> str:
    """The product barcode, or a stable internal code when it has none."""
    return (product.barcode or "").strip() or f"P{product.id:06d}"


def product_specs(session: Session, user: User, items: list[tuple[Product, int]]) -> list[LabelSpec]:
    require_permission(user.permission_codes(), PERM_INVENTORY_VIEW, user.username)
    specs: list[LabelSpec] = []
    for product, copies in items:
        if copies < 1:
            raise LabelError(ar.LABEL_BAD_COPIES)
        specs += [LabelSpec(product.name, product_code(product), format_money(product.sale_price))] * copies
    if len(specs) > MAX_LABELS:
        raise LabelError(ar.LABEL_TOO_MANY)
    return specs


def device_specs(session: Session, user: User, devices: list[Device]) -> list[LabelSpec]:
    """IMEI labels carry no price (the same unit can be re-priced); they show the model and condition."""
    require_permission(user.permission_codes(), PERM_INVENTORY_VIEW, user.username)
    if len(devices) > MAX_LABELS:
        raise LabelError(ar.LABEL_TOO_MANY)
    return [LabelSpec(d.product.name, d.imei1, caption=ar.COND_USED if d.condition == "used" else ar.COND_NEW)
            for d in devices]


def render(specs: list[LabelSpec], path: Path | str, width_mm: float = 50, height_mm: float = 30) -> Path:
    if not specs:
        raise LabelError(ar.LABEL_NOTHING)
    return make_labels_pdf(specs, path, width_mm, height_mm)
