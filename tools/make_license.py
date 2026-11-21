"""OWNER-ONLY tool: create an activation code for a customer's computer. Never ship this file or the key.

    python tools/make_license.py --init                       # once: make a key pair
    python tools/make_license.py CODE --key license_private.key   # sign a customer's machine code

--init prints the public key; paste it into PUBLIC_KEY_B64 in app/core/license.py before building the exe.
"""
import argparse
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("machine_code", nargs="?", help="the code shown on the customer's activation screen")
    ap.add_argument("--key", default=str(Path(__file__).with_name("license_private.key")), help="path of your private key file")
    ap.add_argument("--init", action="store_true", help="create a new key pair (invalidates all old licences)")
    a = ap.parse_args()

    if a.init:
        from cryptography.hazmat.primitives import serialization as s
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        k = Ed25519PrivateKey.generate()
        priv = k.private_bytes(s.Encoding.Raw, s.PrivateFormat.Raw, s.NoEncryption())
        pub = k.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)
        Path(a.key).write_text(base64.b64encode(priv).decode() + "\n")
        print(f"Private key saved to {a.key} (KEEP IT SECRET, back it up).")
        print("Public key for app/core/license.py:", base64.b64encode(pub).decode())
        return 0
    if not a.machine_code:
        ap.error("give the customer's machine code")
    from app.core.license import make_activation_code
    print(make_activation_code(Path(a.key).read_text().strip(), a.machine_code))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
