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


def generate_thermal_receipt_text(
    sale: Sale,
    shop_name: str = "محل الموبايلات",
    footer: str = "شكراً لتعاملكم معنا",
    phone: str = "",
    address: str = "",
) -> str:
    """Generate a clean 80mm text format of the receipt (for printer or preview)."""
    divider = "─" * 40
    lines = [
        f"{shop_name:^40}",
        *([f"{address:^40}"] if address else []),
        *([f"{phone:^40}"] if phone else []),
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
        f"{footer:^40}",
        f"{'البضاعة المباعة ترد وتستبدل خلال 14 يوم':^40}",
        divider,
    ])
    return "\n".join(lines)


def generate_warranty_invoice_pdf(
    sale: Sale,
    dest_path: Path | str,
    shop_name: str = "محل الموبايلات",
    warranty_text: str = "الضمان وفق شروط الوكيل المعتمد",
    shop_phone: str = "",
    shop_address: str = "",
    footer: str = "شكراً لتعاملكم معنا",
) -> Path:
    """Formal A4 sales invoice and warranty certificate (Arabic, right-to-left)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

    from app.printing import pdf_common as pc

    pc.register_fonts()
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(dest), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36,
                            title=f"فاتورة {sale.invoice_no}")
    W = A4[0] - 72

    h1 = pc.style("h1", 18, bold=True, align=pc.TEXT_ALIGN_CENTER, color="#0F172A")
    h2 = pc.style("h2", 13, bold=True, align=pc.TEXT_ALIGN_CENTER, color="#1E3A8A")
    meta = pc.style("meta", 9.5, color="#334155")
    cell = pc.style("cell", 9, align=pc.TEXT_ALIGN_CENTER)
    cell_r = pc.style("cell_r", 9)
    head = pc.style("head", 9.5, bold=True, align=pc.TEXT_ALIGN_CENTER, color="#FFFFFF")
    tot_l = pc.style("tot_l", 9.5, bold=True)
    tot_v = pc.style("tot_v", 9.5, bold=True, align=pc.TEXT_ALIGN_CENTER)

    story = [pc.para(shop_name, h1, W)]
    contact = "  |  ".join(x for x in (shop_address, shop_phone) if x)
    if contact:
        story.append(pc.para(contact, pc.style("c", 9, align=pc.TEXT_ALIGN_CENTER, color="#475569"), W))
    story += [Spacer(1, 4), pc.para(f"فاتورة بيع وشهادة ضمان — رقم {sale.invoice_no}", h2, W), Spacer(1, 12)]

    cust = sale.customer.name if sale.customer else "عميل نقدي"
    cashier = sale.user.full_name if sale.user else "—"
    info = Table([pc.rtl_row([
        pc.para(f"رقم الفاتورة: {sale.invoice_no}", meta, W / 2),
        pc.para(f"التاريخ: {pc.ltr(clock.fmt_local(sale.created_at, '%Y-%m-%d %H:%M'))}", meta, W / 2),
    ]), pc.rtl_row([
        pc.para(f"العميل: {cust}", meta, W / 2),
        pc.para(f"الكاشير: {cashier}", meta, W / 2),
    ])], colWidths=[W / 2, W / 2])
    story += [info, Spacer(1, 12)]

    widths = [28, 185, 105, 38, 78, 78]          # logical order: #, item, IMEI, qty, price, total
    scale = W / sum(widths)
    widths = [w * scale for w in widths]
    headers = ["#", "الصنف", "السيريال (IMEI)", "الكمية", "سعر الوحدة", "الإجمالي"]
    data = [pc.rtl_row([pc.para(h, head, w) for h, w in zip(headers, widths)])]
    for idx, it in enumerate(sale.items, start=1):
        imei = it.device.imei1 if it.device else "—"
        vals = [str(idx), it.product.name, imei, str(it.quantity), format_money(it.unit_price), format_money(it.line_total)]
        data.append(pc.rtl_row([
            pc.para(v, cell_r if i == 1 else cell, widths[i]) for i, v in enumerate(vals)
        ]))
    n_items = len(sale.items)
    items_table = Table(data, colWidths=list(reversed(widths)), repeatRows=1)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
        ("GRID", (0, 0), (-1, n_items), 0.5, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [items_table, Spacer(1, 8)]

    totals = [("المجموع الفرعي", sale.subtotal)]
    if sale.discount > 0:
        totals.append(("الخصم", -sale.discount))
    totals += [("الإجمالي الصافي", sale.total), ("المدفوع", sale.paid)]
    if sale.remaining > 0:
        totals.append(("المتبقي (آجل)", sale.remaining))
    tw = [W * 0.28, W * 0.22]
    ttable = Table([pc.rtl_row([pc.para(label, tot_l, tw[0]), pc.para(format_money(val), tot_v, tw[1])])
                    for label, val in totals], colWidths=list(reversed(tw)), hAlign="RIGHT")
    ttable.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [ttable, Spacer(1, 18)]

    story.append(pc.para("شروط الضمان", pc.style("wh", 11, bold=True, color="#0F172A"), W))
    story.append(pc.para(warranty_text, pc.style("w", 9.5, color="#334155"), W))
    story.append(pc.para("الأجهزة مضمونة ضد عيوب الصناعة. يرجى الاحتفاظ بالفاتورة لتفعيل الضمان.",
                         pc.style("w2", 9.5, color="#334155"), W))
    story += [Spacer(1, 14), pc.para(footer, pc.style("f", 10, bold=True, align=pc.TEXT_ALIGN_CENTER), W)]

    doc.build(story)
    return dest
