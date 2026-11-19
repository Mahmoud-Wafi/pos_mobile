import os
import subprocess
import sys
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(data_dir, *args):
    env = {**os.environ, "POS_DATA_DIR": str(data_dir), "QT_QPA_PLATFORM": "offscreen"}
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "reset_data.py"), *args],
                          env=env, capture_output=True, text=True, timeout=120)


def test_reset_requires_confirmation(tmp_path):
    out = _run(tmp_path)
    assert out.returncode == 1 and not (tmp_path / "shop.db").exists()


def test_reset_gives_empty_shop_with_only_admin(tmp_path):
    assert _run(tmp_path, "--yes").returncode == 0
    con = sqlite3.connect(tmp_path / "shop.db")
    try:
        names = [r[0] for r in con.execute("select name from customers")]
        assert names == ["عميل نقدي"]                       # the built-in cash customer POS needs
        for table in ("products", "devices", "sales", "purchases", "repair_tickets",
                      "warranty_claims", "suppliers", "expenses"):
            assert con.execute(f"select count(*) from {table}").fetchone()[0] == 0, table
        users = con.execute("select username, password_hash from users").fetchall()
        assert [u[0] for u in users] == ["admin"]
    finally:
        con.close()
    from app.core.security import verify_password
    assert verify_password("admin123", users[0][1])


def test_reset_wipes_existing_data_and_keeps_a_backup(tmp_path):
    assert _run(tmp_path, "--yes").returncode == 0
    con = sqlite3.connect(tmp_path / "shop.db")
    con.execute("insert into customers(name, balance, credit_limit, created_at, updated_at) "
                "values ('X', 0, 0, '2026-01-01', '2026-01-01')")
    con.execute("insert into suppliers(name, balance, created_at, updated_at) "
                "values ('S', 0, '2026-01-01', '2026-01-01')")
    con.commit()
    con.close()
    assert _run(tmp_path, "--yes").returncode == 0
    con = sqlite3.connect(tmp_path / "shop.db")
    assert [r[0] for r in con.execute("select name from customers")] == ["عميل نقدي"]
    assert con.execute("select count(*) from suppliers").fetchone()[0] == 0
    con.close()
    assert list((tmp_path / "backups").glob("shop_*.zip"))                # safety backup kept
    assert _run(tmp_path, "--yes", "--everything", "--no-backup").returncode == 0
