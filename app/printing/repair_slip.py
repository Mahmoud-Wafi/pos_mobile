"""Repair intake slip (A5) handed to the customer."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer, Table, TableStyle

from app.core import clock
from app.core.money import format_money
from app.i18n import ar
from app.models.repair import RepairTicket
from app.printing import pdf_common as pc

PAGE_W = A5[0] - 24 * mm


def generate_repair_slip_pdf(ticket: RepairTicket, dest_path: Path | str, shop_name: str = "",
                             shop_phone: str = "") -> Path:
    pc.register_fonts()
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(dest), pagesize=A5, rightMargin=12 * mm, leftMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=ar.REPAIR_SLIP_TITLE)
    h1 = pc.style("h1", 15, bold=True, align=pc.TEXT_ALIGN_CENTER, color="#0F172A")
    h2 = pc.style("h2", 12, bold=True, align=pc.TEXT_ALIGN_CENTER, color="#1E3A8A")
    meta = pc.style("meta", 9, align=pc.TEXT_ALIGN_CENTER, color="#475569")
    key = pc.style("k", 9.5, bold=True, color="#475569")
    val = pc.style("v", 10, color="#0F172A")
    small = pc.style("s", 8.5, align=pc.TEXT_ALIGN_CENTER, color="#64748B", leading=13)

    story = [pc.para(shop_name or ar.APP_TITLE, h1, PAGE_W)]
    if shop_phone:
        story.append(pc.para(shop_phone, meta, PAGE_W))
    story += [Spacer(1, 4), pc.para(ar.REPAIR_SLIP_TITLE, h2, PAGE_W), Spacer(1, 6)]
    rows = [
        (ar.REPAIR_COL_NO, ticket.ticket_no),
        (ar.REPAIR_COL_DATE, clock.fmt_local(ticket.received_at, "%Y-%m-%d %H:%M")),
        (ar.REPAIR_F_CUSTOMER, ticket.customer_name),
        (ar.REPAIR_F_PHONE, ticket.customer_phone or "—"),
        (ar.REPAIR_F_DEVICE, ticket.device_desc),
        (ar.REPAIR_F_IMEI.replace(" (اختياري)", ""), ticket.imei or "—"),
        (ar.REPAIR_F_ISSUE, ticket.issue),
        (ar.REPAIR_F_ESTIMATE.replace(" (ج.م)", ""), format_money(ticket.estimate)),
        (ar.REPAIR_COL_PAID, format_money(ticket.paid)),
    ]
    col_val = PAGE_W * 0.68
    t = Table([pc.rtl_row([pc.para(k, key, PAGE_W * 0.3), pc.para(v, val, col_val)]) for k, v in rows],
              colWidths=[col_val, PAGE_W * 0.32])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [t, Spacer(1, 10), pc.para(ar.REPAIR_SLIP_TERMS, small, PAGE_W)]
    doc.build(story)
    return dest
