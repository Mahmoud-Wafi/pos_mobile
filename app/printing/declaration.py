"""Used device sale & ownership non-theft declaration PDF generator.

Creates an official A4 legal declaration document certifying the seller
owns the used device, it is not stolen, and they received the purchase amount.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.core.money import format_money
from app.models.purchase import UsedDevicePurchase


def generate_used_device_declaration_pdf(
    used_purchase: UsedDevicePurchase,
    dest_path: Path | str,
    shop_name: str = "محل الموبايلات",
) -> Path:
    """Generate a formal A4 Used Mobile Device Sale & Ownership Declaration PDF."""
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(dest),
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    header_shop_style = ParagraphStyle(
        "ShopTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=1,  # Center
        textColor=colors.HexColor("#0F172A"),
    )

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        alignment=1,
        textColor=colors.HexColor("#1E3A8A"),
    )

    legal_text_style = ParagraphStyle(
        "LegalNotice",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=16,
        alignment=0,
        textColor=colors.HexColor("#1E293B"),
    )

    meta_style = ParagraphStyle(
        "MetaText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#475569"),
    )

    story = []

    # Shop Name & Declaration Header
    story.append(Paragraph(f"<b>{shop_name}</b>", header_shop_style))
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            "<b>Used Mobile Device Sale &amp; Ownership Declaration / إقرار بيع وتنازل ملكية جهاز مستعمل</b>",
            title_style,
        )
    )
    story.append(Spacer(1, 4))
    date_str = used_purchase.created_at.strftime("%Y-%m-%d  %I:%M %p")
    story.append(
        Paragraph(
            f"Declaration Ref: #UDP-{used_purchase.id:05d}  |  Date: {date_str}",
            ParagraphStyle("CenterMeta", parent=meta_style, alignment=1),
        )
    )
    story.append(Spacer(1, 14))

    # Seller Information Box
    story.append(Paragraph("<b>1. Seller Information / بيانات البائع المتنازل:</b>", legal_text_style))
    story.append(Spacer(1, 4))

    seller_rows = [
        [
            "Full Name / اسم البائع الرباعي:",
            used_purchase.seller_name,
            "National ID / الرقم القومي:",
            used_purchase.seller_national_id,
        ],
        [
            "Phone / رقم الهاتف:",
            used_purchase.seller_phone,
            "Purchasing Staff / المستلم:",
            used_purchase.user.full_name if used_purchase.user else "Staff",
        ],
    ]
    seller_table = Table(seller_rows, colWidths=[140, 130, 130, 120])
    seller_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(seller_table)
    story.append(Spacer(1, 14))

    # Device Information Box
    story.append(Paragraph("<b>2. Device Specifications &amp; Purchase Price / بيانات الجهاز والسعر:</b>", legal_text_style))
    story.append(Spacer(1, 4))

    device = used_purchase.device
    dev_name = device.product.name if device and device.product else "Mobile Device"
    imei1 = device.imei1 if device else "—"
    imei2 = device.imei2 if (device and device.imei2) else "—"
    price_str = f"{format_money(used_purchase.price)}"

    device_rows = [
        ["Device / نوع وموديل الجهاز:", dev_name, "Condition / الحالة:", "Used / مستعمل"],
        ["IMEI 1 / السيريال الأول:", imei1, "IMEI 2 / السيريال الثاني:", imei2],
        [
            "Purchase Price / مبلغ الشراء:",
            f"<b>{price_str}</b>",
            "Payment / طريقة الدفع:",
            "Cash / نقداً من الدرج",
        ],
        [
            "Inspection Notes / ملاحظات الفحص:",
            used_purchase.condition_notes or "Passed standard inspection / فحص مطابق",
            "",
            "",
        ],
    ]
    device_table = Table(device_rows, colWidths=[140, 130, 130, 120])
    device_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0F172A")),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("SPAN", (1, 3), (3, 3)),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(device_table)
    story.append(Spacer(1, 16))

    # Legal Declaration Statement
    story.append(Paragraph("<b>3. Legal Declaration &amp; Non-Theft Pledge / نص الإقرار والتعهد القانوني:</b>", legal_text_style))
    story.append(Spacer(1, 4))

    pledge_text = (
        "<b>تعهد وإقرار صريح:</b> أقر أنا الموقع أدناه وبكامل قواي العقلية وإرادتي الحرة، وبصفتي المالك الشرعي والقانوني "
        "الوحيد للجهاز الموضحة بياناته وأرقامه التسلسلية (IMEI) أعلاه، بأن الجهاز ملكي الشخصي الخالص وليس مسروقاً أو "
        "مختلساً أو محلاً لأي بلاغ سرقة أو نزاع قضائي أو حظر أمني. وأتحمل وحدي كامل المسؤولية الجنائية والمدنية "
        "والتعويضات القانونية أمام كافة الجهات الرسمية والقضائية في جمهورية مصر العربية حال ثبوت خلاف ذلك، "
        "كما أقر باستلامي كامل المبلغ النقدي الموضح بعاليه من المحل بصورة نهائية وباتة.<br/><br/>"
        "<i>I hereby certify under penalty of law that I am the sole, lawful owner of the device listed above, that it is not "
        "stolen or subject to any dispute or legal claim, and that I have received the full agreed purchase price in cash.</i>"
    )
    pledge_box = Table([[Paragraph(pledge_text, legal_text_style)]], colWidths=[520])
    pledge_box.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#3B82F6")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ])
    )
    story.append(pledge_box)
    story.append(Spacer(1, 24))

    # Signature & Thumbprint Blocks
    sign_rows = [
        [
            "توقيع البائع (Seller Signature)\n\n\n__________________________",
            "بصمة إبهام البائع (Thumbprint)\n\n\n[                      ]",
            "توقيع المستلم وختم المحل\n\n\n__________________________",
        ]
    ]
    sign_table = Table(sign_rows, colWidths=[175, 170, 175])
    sign_table.setStyle(
        TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ])
    )
    story.append(sign_table)

    doc.build(story)
    return dest

