"""Per-machine licence (D-021)."""
import base64

import pytest
from cryptography.hazmat.primitives import serialization as s
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import license as lic


@pytest.fixture
def keys(monkeypatch):
    k = Ed25519PrivateKey.generate()
    pub = k.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)
    monkeypatch.setattr(lic, "PUBLIC_KEY_B64", base64.b64encode(pub).decode())
    return base64.b64encode(k.private_bytes(s.Encoding.Raw, s.PrivateFormat.Raw, s.NoEncryption())).decode()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("POS_DATA_DIR", str(tmp_path))
    return tmp_path


def test_machine_code_is_stable_and_formatted():
    c = lic.machine_code()
    assert c == lic.machine_code()
    assert len(c.replace("-", "")) == 20 and c.count("-") == 3


def test_valid_code_for_this_machine_activates_and_persists(keys, data_dir):
    assert not lic.is_licensed()
    code = lic.make_activation_code(keys, lic.machine_code())
    assert lic.activate(code)
    assert lic.is_licensed()


def test_code_made_for_another_machine_is_rejected(keys, data_dir):
    other = lic.make_activation_code(keys, "AAAAA-BBBBB-CCCCC-DDDDD")
    assert not lic.activate(other)
    assert not lic.is_licensed()


def test_tampered_or_garbage_code_is_rejected(keys, data_dir):
    code = lic.make_activation_code(keys, lic.machine_code())
    assert not lic.verify_activation(code[:-3] + "AAA")
    for bad in ("", "   ", "not-a-code", "!!!"):
        assert not lic.verify_activation(bad)


def test_code_signed_by_a_different_key_is_rejected(keys, data_dir):
    rogue = Ed25519PrivateKey.generate()
    rogue_b64 = base64.b64encode(rogue.private_bytes(s.Encoding.Raw, s.PrivateFormat.Raw, s.NoEncryption())).decode()
    assert not lic.verify_activation(lic.make_activation_code(rogue_b64, lic.machine_code()))


def test_copied_licence_file_does_not_work_on_another_machine(keys, data_dir, monkeypatch):
    lic.activate(lic.make_activation_code(keys, lic.machine_code()))
    monkeypatch.setattr(lic, "_raw_machine_id", lambda: "some-other-computer")
    assert not lic.is_licensed()


def test_code_tolerates_spacing_case_and_dashes(keys, data_dir):
    code = lic.make_activation_code(keys, lic.machine_code())
    assert lic.verify_activation("  " + code.lower().replace("-", " ") + "\n")


def test_dialog_activates_with_valid_code(qtbot, keys, data_dir):
    from app.ui.license_dialog import ActivationDialog
    d = ActivationDialog()
    qtbot.addWidget(d)
    assert d.machine_edit.text() == lic.machine_code()
    d.code_edit.setPlainText(lic.make_activation_code(keys, lic.machine_code()))
    d._activate()
    assert d.result() == d.DialogCode.Accepted and lic.is_licensed()


def test_shipped_public_key_matches_a_real_key():
    base64.b64decode(lic.PUBLIC_KEY_B64)
    assert len(base64.b64decode(lic.PUBLIC_KEY_B64)) == 32
