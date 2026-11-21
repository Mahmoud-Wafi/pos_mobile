"""Per-machine licence: the app runs only on a computer the owner has activated (D-021).

How it works (fully offline):
  1. The app shows a *machine code* (a hash of this computer's OS install id).
  2. The owner signs that code with his private key (tools/make_license.py) -> *activation code*.
  3. The app checks the signature with the public key below and that it was made for THIS machine.
The private key never ships with the app, so a customer cannot create codes for other computers.
"""
from __future__ import annotations

import base64
import hashlib
import subprocess
import sys
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PUBLIC_KEY_B64 = "F6BQ+/N2ba4hBtgP3yAQ+AAQvMeg5OTyp7Avmstsw9I="
_SALT = "mobile-shop-pos|license|v1|"
_PREFIX = b"POSLIC1|"
LICENSE_FILE = "license.key"


def _raw_machine_id() -> str:
    """A stable id of this OS installation (not the user account)."""
    try:
        if sys.platform.startswith("win"):
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        if sys.platform == "darwin":
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                 capture_output=True, text=True, timeout=5).stdout
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split('"')[-2]
        for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            if Path(p).exists():
                return Path(p).read_text().strip()
    except Exception:
        pass
    return str(uuid.getnode())


def machine_code() -> str:
    """The code the customer sends to the owner: 20 hex chars in groups of 5."""
    digest = hashlib.sha256((_SALT + _raw_machine_id()).encode()).hexdigest().upper()[:20]
    return "-".join(digest[i:i + 5] for i in range(0, 20, 5))


def _clean(text: str) -> str:
    return "".join((text or "").split()).replace("-", "").upper()


def _signed_message(code: str) -> bytes:
    return _PREFIX + _clean(code).encode()


def make_activation_code(private_key_b64: str, machine: str) -> str:
    """Owner side (tools/make_license.py): sign a customer's machine code."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    sig = base64.b32encode(key.sign(_signed_message(machine))).decode().rstrip("=")
    return "-".join(sig[i:i + 8] for i in range(0, len(sig), 8))


def verify_activation(activation: str, machine: str | None = None) -> bool:
    """True if *activation* is a valid signature of this machine's code (or *machine*)."""
    machine = machine or machine_code()
    raw = _clean(activation)
    if not raw:
        return False
    try:
        sig = base64.b32decode(raw + "=" * (-len(raw) % 8))
        Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY_B64)).verify(sig, _signed_message(machine))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def license_path() -> Path:
    from app.core.paths import default_data_dir
    return default_data_dir() / LICENSE_FILE


def is_licensed() -> bool:
    try:
        return verify_activation(license_path().read_text(encoding="utf-8"))
    except OSError:
        return False


def activate(activation: str) -> bool:
    """Verify and store the activation code. Returns False (and stores nothing) if it is not valid here."""
    if not verify_activation(activation):
        return False
    p = license_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_clean(activation) + "\n", encoding="utf-8")
    return True
