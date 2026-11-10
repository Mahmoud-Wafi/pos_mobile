"""Printing and PDF invoice generator (80mm thermal receipt & A4 warranty invoice).

Isolated so it runs cross-platform and can be mocked in tests.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Optional

from app.core import clock
from app.core.money import format_money
from app.core.money import piasters_to_egp
from app.models.sale import Sale


def generate_thermal_receipt_text(sale: Sale, shop_name: str = "محل الموبايلات") -> str:
    """Generate a clean 80mm text format of the receipt (for printer or preview)."""
    divider = "─" * 40
    lines = [
        f"{shop_name:^40}",
        f"{'فاتورة مبيعات نقدية':^40}",
        divider,
        f"رقم الفاتورة: {sale.invoice_no}",
        f"التاريخ: {clock.fmt_local(sale.created_at, '%Y-%m-%d  %I:%M %p')}",
        f"الكاشير: {sale.user.full_name if sale.user else '—'}",
        f"العميل: {sale.customer.name if sale.customer else 'عميل نقدي'}",
        divider,
        f"{'الصنف':<20}{'الكمية':^6}{'الإجمالي':>14}",
        divider,
    ]

    for item in sale.items:
        name = item.product.name[:20]
        if item.device:
            name += f"\n  IMEI: {item.device.imei1}"
        lines.append(f"{name:<20}{item.quantity:^6}{format_money(item.line_total):>14}")

    lines.extend([
        divider,
        f"{'المجموع الفرعي:':<24}{format_money(sale.subtotal):>16}",
    ])
    if sale.discount > 0:
        lines.append(f"{'الخصم الممنوح:':<24}{format_money(sale.discount):>16}")

    lines.extend([
        f"{'الإجمالي الصافي:':<24}{format_money(sale.total):>16}",
        f"{'المدفوع:':<24}{format_money(sale.paid):>16}",
    ])
    if sale.remaining > 0:
        lines.append(f"{'المتبقي (آجل):':<24}{format_money(sale.remaining):>16}")

    lines.extend([
        divider,
        f"{'شكراً لتعاملكم معنا':^40}",
        f"{'البضاعة المباعة ترد وتستبدل خلال 14 يوم':^40}",
        divider,
    ])
    return "\n".join(lines)


def generate_warranty_invoice_pdf(
    sale: Sale,
    dest_path: Path | str,
    shop_name: str = "محل الموبايلات",
    warranty_text: str = "الضمان وفق شروط الوكيل المعتمد",
) -> Path:
    """Generate a formal A4 sales and warranty certificate invoice PDF using ReportLab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

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
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=1,  # Center
        textColor=colors.HexColor("#0F172A"),
    )
    meta_style = ParagraphStyle(
        "InvoiceMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#334155"),
    )

    story = []

    # Title & Header
    story.append(Paragraph(f"<b>{shop_name}</b>", title_style))
    story.append(Paragraph(f"Sales Invoice &amp; Warranty Certificate — #{sale.invoice_no}", title_style))
    story.append(Spacer(1, 14))

    # Meta Info Table
    meta_data = [
        [f"Invoice: {sale.invoice_no}", f"Date: {clock.fmt_local(sale.created_at, '%Y-%m-%d %H:%M')}"],
        [f"Customer: {sale.customer.name}", f"Cashier: {sale.user.full_name if sale.user else 'Admin'}"],
    ]
    meta_table = Table(meta_data, colWidths=[260, 260])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 16))

    # Items Table
    table_data = [["#", "Item Description", "IMEI / Serial", "Qty", "Unit Price", "Total (EGP)"]]
    for idx, it in enumerate(sale.items, start=1):
        imei_str = it.device.imei1 if it.device else "—"
        price_egp = f"{piasters_to_egp(it.unit_price):,.2f}"
        total_egp = f"{piasters_to_egp(it.line_total):,.2f}"
        table_data.append([str(idx), it.product.name, imei_str, str(it.quantity), price_egp, total_egp])

    # Totals rows
    table_data.append(["", "", "", "", "Subtotal:", f"{piasters_to_egp(sale.subtotal):,.2f}"])
    if sale.discount > 0:
        table_data.append(["", "", "", "", "Discount:", f"-{piasters_to_egp(sale.discount):,.2f}"])
    table_data.append(["", "", "", "", "Net Total:", f"{piasters_to_egp(sale.total):,.2f}"])
    table_data.append(["", "", "", "", "Paid:", f"{piasters_to_egp(sale.paid):,.2f}"])
    if sale.remaining > 0:
        table_data.append(["", "", "", "", "Remaining:", f"{piasters_to_egp(sale.remaining):,.2f}"])

    items_table = Table(table_data, colWidths=[30, 180, 120, 40, 80, 80])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, len(sale.items)), 0.5, colors.HexColor("#CBD5E1")),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 20))

    # Warranty notice
    story.append(Paragraph(f"<b>Warranty Terms:</b> {warranty_text}", meta_style))
    story.append(Spacer(1, 8))
    story.append(Paragraph("All devices are guaranteed against manufacturer defects. Keep this invoice for warranty claims.", meta_style))

    doc.build(story)
    return dest

