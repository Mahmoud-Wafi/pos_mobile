"""Warranty claims: open a case against a sold item, move it through repair, close it. Audited."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import clock
from app.core.audit import log_action
from app.core.permissions import PERM_SALES_RETURN, require_permission
from app.i18n import ar
from app.models.sale import SaleItem
from app.models.user import User
from app.models.warranty import CLAIM_STATUSES, WarrantyClaim


class WarrantyError(Exception):
    """Business error with an Arabic message."""


_OPEN = ("open", "in_repair")


def open_claim(session: Session, user: User, sale_item_id: int, issue: str) -> WarrantyClaim:
    """Open a claim. An expired warranty is allowed (goodwill) but recorded as ``in_warranty=False``."""
    require_permission(user.permission_codes(), PERM_SALES_RETURN, user.username)
    issue = (issue or "").strip()
    if not issue:
        raise WarrantyError(ar.WARRANTY_ISSUE_REQUIRED)
    item = session.get(SaleItem, sale_item_id)
    if item is None or item.sale.status != "posted":
        raise WarrantyError(ar.WARRANTY_ITEM_INVALID)
    already = (session.query(WarrantyClaim)
               .filter(WarrantyClaim.sale_item_id == item.id, WarrantyClaim.status.in_(_OPEN)).first())
    if already is not None:
        raise WarrantyError(ar.WARRANTY_CLAIM_EXISTS)
    in_warranty = item.warranty_end_date is not None and item.warranty_end_date >= clock.utcnow()
    claim = WarrantyClaim(sale_item_id=item.id, device_id=item.device_id, issue=issue,
                          in_warranty=in_warranty, opened_by=user.id)
    session.add(claim)
    session.flush()
    log_action(session, "warranty_claim_open", user_id=user.id, table_name="warranty_claims",
               record_id=claim.id, new_value={"sale_item_id": item.id, "in_warranty": in_warranty})
    return claim


def update_claim(session: Session, user: User, claim_id: int, status: str, resolution: str = "") -> WarrantyClaim:
    require_permission(user.permission_codes(), PERM_SALES_RETURN, user.username)
    if status not in CLAIM_STATUSES:
        raise WarrantyError(ar.WARRANTY_BAD_STATUS)
    claim = session.get(WarrantyClaim, claim_id)
    if claim is None:
        raise WarrantyError(ar.WARRANTY_ITEM_INVALID)
    if claim.status in ("resolved", "rejected"):
        raise WarrantyError(ar.WARRANTY_CLAIM_CLOSED)
    resolution = (resolution or "").strip()
    if status in ("resolved", "rejected") and not resolution:
        raise WarrantyError(ar.WARRANTY_RESOLUTION_REQUIRED)
    old = claim.status
    claim.status = status
    if resolution:
        claim.resolution = resolution
    if status in ("resolved", "rejected"):
        claim.closed_at = clock.utcnow()
    log_action(session, "warranty_claim_update", user_id=user.id, table_name="warranty_claims",
               record_id=claim.id, old_value={"status": old}, new_value={"status": status})
    return claim


def list_claims(session: Session, user: User, status: str | None = None, sale_item_id: int | None = None
                ) -> list[WarrantyClaim]:
    require_permission(user.permission_codes(), PERM_SALES_RETURN, user.username)
    q = session.query(WarrantyClaim)
    if status:
        q = q.filter(WarrantyClaim.status == status)
    if sale_item_id:
        q = q.filter(WarrantyClaim.sale_item_id == sale_item_id)
    return q.order_by(WarrantyClaim.opened_at.desc(), WarrantyClaim.id.desc()).all()
