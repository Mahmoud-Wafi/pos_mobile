import pytest
from pypdf import PdfReader

from app.core.money import egp_to_piasters as egp
from app.core.permissions import ROLE_MANAGER
from app.core.security import hash_password
from app.models.user import Role, User
from app.printing.labels import LabelSpec, make_labels_pdf
from app.services import inventory_service, label_service


def test_one_page_per_label_with_requested_size(tmp_path):
    out = make_labels_pdf([LabelSpec("هاتف سامسونج A15", "6221234567890", "5,000.00 ج.م"),
                           LabelSpec("Phone", "352001111222333", caption="جديد")], tmp_path / "l.pdf", 50, 30)
    pages = PdfReader(str(out)).pages
    assert len(pages) == 2
    assert round(float(pages[0].mediabox.width) / 2.8346) == 50
    assert round(float(pages[0].mediabox.height) / 2.8346) == 30


def test_empty_and_blank_code_rejected(tmp_path):
    with pytest.raises(ValueError):
        make_labels_pdf([], tmp_path / "x.pdf")
    with pytest.raises(ValueError):
        make_labels_pdf([LabelSpec("x", "  ")], tmp_path / "x.pdf")


def test_service_specs_from_products_and_devices(db_session, tmp_path):
    s = db_session
    r = s.query(Role).filter_by(name=ROLE_MANAGER).first()
    mgr = User(username="lm", password_hash=hash_password("Passw0rd!"), full_name="l", role_id=r.id)
    s.add(mgr)
    s.commit()
    p = inventory_service.create_product(s, mgr, {
        "name": "شاحن", "type": "accessory", "cost_price": egp("10"), "sale_price": egp("50"),
        "min_price": egp("20"), "min_stock": 1, "track_imei": False, "warranty_days": 0})
    phone = inventory_service.create_product(s, mgr, {
        "name": "Phone", "type": "phone", "cost_price": egp("100"), "sale_price": egp("200"),
        "min_price": egp("150"), "min_stock": 0, "track_imei": True, "warranty_days": 365})
    devs = inventory_service.add_devices(s, mgr, phone, [{"imei1": "490154203237518", "condition": "used"}])
    s.commit()
    specs = label_service.product_specs(s, mgr, [(p, 3)])
    assert len(specs) == 3 and specs[0].code == f"P{p.id:06d}" and "50" in specs[0].price_text
    dspecs = label_service.device_specs(s, mgr, devs)
    assert dspecs[0].code == "490154203237518" and dspecs[0].price_text == ""
    assert label_service.render(specs + dspecs, tmp_path / "all.pdf").exists()
    with pytest.raises(label_service.LabelError):
        label_service.product_specs(s, mgr, [(p, 0)])
