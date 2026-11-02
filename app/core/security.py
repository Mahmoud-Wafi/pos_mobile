"""Password hashing and verification using bcrypt.

Lockout logic lives here so services stay thin.
"""
import datetime
from typing import Optional

import bcrypt

from app.config import MAX_FAILED_ATTEMPTS, LOCKOUT_MINUTES


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def is_account_locked(failed_attempts: int, locked_until: Optional[datetime.datetime]) -> bool:
    """Return True if the account should be considered locked right now."""
    if locked_until is not None and datetime.datetime.utcnow() < locked_until:
        return True
    return False


def compute_lockout(failed_attempts: int) -> Optional[datetime.datetime]:
    """Return a new *locked_until* datetime when threshold is hit, else None."""
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        return datetime.datetime.utcnow() + datetime.timedelta(minutes=LOCKOUT_MINUTES)
    return None

