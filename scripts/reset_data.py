"""Wipe all shop data and start clean: only the admin account (admin / admin123) remains.

CLOSE THE APP FIRST. Usage (from the project folder):

    python scripts/reset_data.py --yes                 # reset, keeping a safety backup
    python scripts/reset_data.py --yes --no-backup     # reset without a safety backup
    python scripts/reset_data.py --yes --everything    # also delete old backups and generated PDFs

Set POS_DATA_DIR to reset a different data folder.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yes", action="store_true", help="confirm that you want to erase everything")
    ap.add_argument("--no-backup", action="store_true", help="do not keep a safety backup of the old data")
    ap.add_argument("--everything", action="store_true", help="also delete old backups and generated PDFs")
    args = ap.parse_args()

    from app.core.reset import data_dir, reset_database

    if not args.yes:
        print(f"This will ERASE all data in {data_dir()}.\nRun again with --yes to confirm.")
        return 1
    safety = reset_database(keep_backup=not args.no_backup, wipe_backups=args.everything,
                            wipe_files=args.everything)
    print(f"Done. Data folder: {data_dir()}")
    if safety:
        print(f"Safety backup of the old data: {safety}")
    print("Sign in with  admin / admin123  (change the password after the first login).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
