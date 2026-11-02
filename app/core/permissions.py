"""Permission constants and enforcement helpers.

All permission codes are defined here as string constants.
Services call `require_permission(session, user, PERM_*)` which raises
`PermissionDenied` if the user lacks the permission.
"""


# ── System ────────────────────────────────────────────────────────────────────
PERM_AUDIT_VIEW = "audit.view"
PERM_SETTINGS_MANAGE = "settings.manage"
PERM_USERS_MANAGE = "users.manage"
PERM_BACKUP_MANAGE = "backup.manage"

# ── Sales ────────────────────────────────────────────────────────────────────
PERM_SALES_CREATE = "sales.create"
PERM_SALES_DISCOUNT = "sales.discount"
PERM_SALES_VOID = "sales.void"
PERM_SALES_RETURN = "sales.return"
PERM_SALES_BELOW_MIN_PRICE = "sales.below_min_price"

# ── Inventory ────────────────────────────────────────────────────────────────
PERM_INVENTORY_VIEW = "inventory.view"
PERM_INVENTORY_EDIT = "inventory.edit"
PERM_INVENTORY_ADJUST = "inventory.adjust"

# ── Cost / Profit ─────────────────────────────────────────────────────────────
PERM_COST_VIEW = "cost.view"
PERM_PROFIT_VIEW = "profit.view"

# ── Purchases ────────────────────────────────────────────────────────────────
PERM_PURCHASES_CREATE = "purchases.create"
PERM_PURCHASES_VIEW = "purchases.view"

# ── Customers ────────────────────────────────────────────────────────────────
PERM_CUSTOMERS_MANAGE = "customers.manage"
PERM_CUSTOMERS_COLLECT = "customers.collect"

# ── Wallets ──────────────────────────────────────────────────────────────────
PERM_WALLET_USE = "wallet.use"
PERM_WALLET_MANAGE = "wallet.manage"
PERM_WALLET_AUDIT = "wallet.audit"

# ── Cash ─────────────────────────────────────────────────────────────────────
PERM_CASH_VIEW = "cash.view"
PERM_CASH_EXPENSE = "cash.expense"
PERM_CASH_CLOSE_DAY = "cash.close_day"

# ── Reports ──────────────────────────────────────────────────────────────────
PERM_REPORTS_VIEW = "reports.view"
PERM_REPORTS_PROFIT = "reports.profit"

# ── Role definitions (seed data) ─────────────────────────────────────────────
ROLE_MANAGER = "manager"
ROLE_CASHIER = "cashier"
ROLE_WALLET_EMPLOYEE = "wallet_employee"

MANAGER_PERMISSIONS: list[str] = [
    PERM_AUDIT_VIEW, PERM_SETTINGS_MANAGE, PERM_USERS_MANAGE, PERM_BACKUP_MANAGE,
    PERM_SALES_CREATE, PERM_SALES_DISCOUNT, PERM_SALES_VOID, PERM_SALES_RETURN,
    PERM_SALES_BELOW_MIN_PRICE,
    PERM_INVENTORY_VIEW, PERM_INVENTORY_EDIT, PERM_INVENTORY_ADJUST,
    PERM_COST_VIEW, PERM_PROFIT_VIEW,
    PERM_PURCHASES_CREATE, PERM_PURCHASES_VIEW,
    PERM_CUSTOMERS_MANAGE, PERM_CUSTOMERS_COLLECT,
    PERM_WALLET_USE, PERM_WALLET_MANAGE, PERM_WALLET_AUDIT,
    PERM_CASH_VIEW, PERM_CASH_EXPENSE, PERM_CASH_CLOSE_DAY,
    PERM_REPORTS_VIEW, PERM_REPORTS_PROFIT,
]

CASHIER_PERMISSIONS: list[str] = [
    PERM_SALES_CREATE, PERM_SALES_DISCOUNT, PERM_SALES_RETURN,
    PERM_INVENTORY_VIEW,
    PERM_CUSTOMERS_MANAGE, PERM_CUSTOMERS_COLLECT,
    PERM_WALLET_USE,
    PERM_CASH_VIEW, PERM_CASH_EXPENSE,
    PERM_REPORTS_VIEW,
    PERM_PURCHASES_VIEW,
]

WALLET_EMPLOYEE_PERMISSIONS: list[str] = [
    PERM_WALLET_USE,
]


class PermissionDenied(Exception):
    """Raised when a user lacks a required permission."""

    def __init__(self, permission_code: str, username: str = ""):
        self.permission_code = permission_code
        self.username = username
        msg = f"المستخدم '{username}' لا يملك صلاحية: {permission_code}"
        super().__init__(msg)


def has_permission(user_permissions: set[str], permission_code: str) -> bool:
    """Return True if *permission_code* is in the user's permission set."""
    return permission_code in user_permissions


def require_permission(user_permissions: set[str], permission_code: str, username: str = "") -> None:
    """Raise PermissionDenied if the user lacks *permission_code*."""
    if not has_permission(user_permissions, permission_code):
        raise PermissionDenied(permission_code, username)
