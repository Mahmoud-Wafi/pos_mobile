"""Used-device sale & ownership declaration (A4, Arabic RTL).

Certifies that the seller owns the device, it is not stolen, and they received the price.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

from app.core import clock
from app.core.money import format_money
from app.models.purchase import UsedDevicePurchase
from app.printing import pdf_common as pc

PAGE_W = A4[0] - 72     # usable width (36pt margins)

PLEDGE_AR = (
    "تعهد وإقرار صريح: أقر أنا الموقع أدناه وبكامل قواي العقلية وإرادتي الحرة، وبصفتي المالك الشرعي والقانوني "
    "الوحيد للجهاز الموضحة بياناته وأرقامه التسلسلية (IMEI) أعلاه، بأن الجهاز ملكي الشخصي الخالص وليس مسروقاً أو "
    "مختلساً أو محلاً لأي بلاغ سرقة أو نزاع قضائي أو حظر أمني. وأتحمل وحدي كامل المسؤولية الجنائية والمدنية "
    "والتعويضات القانونية أمام كافة الجهات الرسمية والقضائية في جمهورية مصر العربية حال ثبوت خلاف ذلك، "
    "كما أقر باستلامي كامل المبلغ النقدي الموضح بعاليه من المحل بصورة نهائية وباتة."
)
PLEDGE_EN = (
    "I hereby certify that I am the sole, lawful owner of the device listed above, that it is not stolen "
    "or subject to any dispute or legal claim, and that I have received the full agreed purchase price in cash."
)


def _kv_table(rows: list[list[tuple[str, str]]], col_w: float) -> Table:
    """rows of (label, value) pairs; two pairs per row, laid out right-to-left."""
    label_st = pc.style("lbl", 9, bold=True, color="#0F172A")
    val_st = pc.style("val", 9)
    data = []
    for row in rows:
        cells = []
        for label, value in row:
            cells += [pc.para(label, label_st, col_w), pc.para(value, val_st, col_w)]
        data.append(pc.rtl_row(cells))
    t = Table(data, colWidths=[col_w] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def generate_used_device_declaration_pdf(
    used_purchase: UsedDevicePurchase,
    dest_path: Path | str,
    shop_name: str = "محل الموبايلات",
    shop_phone: str = "",
    shop_address: str = "",
) -> Path:
    pc.register_fonts()
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(dest), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
                            title="إقرار بيع وتنازل ملكية جهاز مستعمل")

    h1 = pc.style("h1", 18, bold=True, align=pc.TEXT_ALIGN_CENTER, color="#0F172A")
    h2 = pc.style("h2", 14, bold=True, align=pc.TEXT_ALIGN_CENTER, color="#1E3A8A")
    meta = pc.style("meta", 9, align=pc.TEXT_ALIGN_CENTER, color="#475569")
    sec = pc.style("sec", 11, bold=True, color="#0F172A")
    body = pc.style("body", 10.5, leading=19)
    body_en = pc.style("body_en", 8.5, align=pc.TEXT_ALIGN_LEFT, color="#475569", leading=12)

    story = [pc.para(shop_name, h1, PAGE_W)]
    contact = "  |  ".join(x for x in (shop_address, shop_phone) if x)
    if contact:
        story.append(pc.para(contact, meta, PAGE_W))
    story += [Spacer(1, 6), pc.para("إقرار بيع وتنازل ملكية جهاز مستعمل", h2, PAGE_W), Spacer(1, 4)]
    story.append(pc.para(
        f"رقم الإقرار: UDP-{used_purchase.id:05d}   |   التاريخ: {pc.ltr(clock.fmt_local(used_purchase.created_at, '%Y-%m-%d %H:%M'))}",
        meta, PAGE_W))
    story.append(Spacer(1, 14))

    col_w = PAGE_W / 4
    story += [pc.para("١. بيانات البائع المتنازل", sec, PAGE_W), Spacer(1, 4), _kv_table([
        [("اسم البائع", used_purchase.seller_name), ("الرقم القومي", used_purchase.seller_national_id)],
        [("رقم الهاتف", used_purchase.seller_phone),
         ("المستلم", used_purchase.user.full_name if used_purchase.user else "—")],
    ], col_w), Spacer(1, 14)]

    device = used_purchase.device
    dev_name = device.product.name if device and device.product else "جهاز محمول"
    story += [pc.para("٢. بيانات الجهاز والسعر", sec, PAGE_W), Spacer(1, 4), _kv_table([
        [("الجهاز", dev_name), ("الحالة", "مستعمل")],
        [("IMEI 1", device.imei1 if device else "—"), ("IMEI 2", device.imei2 if device and device.imei2 else "—")],
        [("مبلغ الشراء", format_money(used_purchase.price)), ("طريقة الدفع", "نقداً من الدرج")],
        [("ملاحظات الفحص", used_purchase.condition_notes or "فحص مطابق"), ("", "")],
    ], col_w), Spacer(1, 16)]

    story += [pc.para("٣. نص الإقرار والتعهد القانوني", sec, PAGE_W), Spacer(1, 4)]
    pledge = Table([[pc.para(PLEDGE_AR, body, PAGE_W - 30)], [pc.para(PLEDGE_EN, body_en, PAGE_W - 30)]],
                   colWidths=[PAGE_W])
    pledge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#3B82F6")),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story += [pledge, Spacer(1, 28)]

    sign_st = pc.style("sign", 9.5, align=pc.TEXT_ALIGN_CENTER, color="#334155", leading=15)
    sign = Table([pc.rtl_row([
        pc.para("توقيع البائع\n\n\n______________________", sign_st, PAGE_W / 3),
        pc.para("بصمة إبهام البائع\n\n\n[                    ]", sign_st, PAGE_W / 3),
        pc.para("توقيع المستلم وختم المحل\n\n\n______________________", sign_st, PAGE_W / 3),
    ])], colWidths=[PAGE_W / 3] * 3)
    sign.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(sign)

    doc.build(story)
    return dest
