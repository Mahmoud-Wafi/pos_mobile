"""Maps screens to the permissions they need (UI hint only).

The service layer remains the real enforcement point (D-005); this module only
decides which screens and buttons are shown so users never hit raw errors.
A screen is shown when the user holds ANY permission of its set; an empty set
means "any logged-in user".
"""
from __future__ import annotations

from app.core import permissions as P

NAV_PERMISSIONS: dict[str, set[str]] = {
    "dashboard": set(),
    "pos": {P.PERM_SALES_CREATE},
    "inventory": {P.PERM_INVENTORY_VIEW},
    "returns": {P.PERM_SALES_RETURN},
    "purchases": {P.PERM_PURCHASES_VIEW, P.PERM_PURCHASES_CREATE},
    "wallets": {P.PERM_WALLET_USE, P.PERM_WALLET_MANAGE},
    "accounting": {P.PERM_CASH_VIEW},
    "customers": {P.PERM_CUSTOMERS_MANAGE},
    "reports": {P.PERM_REPORTS_VIEW},
    "settings": {P.PERM_SETTINGS_MANAGE, P.PERM_BACKUP_MANAGE},
}


def can_open(user_permissions: set[str], screen: str) -> bool:
    required = NAV_PERMISSIONS.get(screen, set())
    return not required or bool(required & set(user_permissions))


def allowed_screens(user_permissions: set[str]) -> list[str]:
    return [s for s in NAV_PERMISSIONS if can_open(user_permissions, s)]
