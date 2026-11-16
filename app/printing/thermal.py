"""80 mm thermal receipt as RTL HTML (printed through Qt, so any installed printer works)."""
from __future__ import annotations

from html import escape

from app.core import clock
from app.core.money import format_money
from app.i18n import ar
from app.models.sale import Sale

RECEIPT_WIDTH_MM = 80
MARGIN_MM = 3


def receipt_html(sale: Sale, cfg: dict[str, str]) -> str:
    """Build the receipt. ``cfg`` is settings_service.get_all(): shop_name/phone/address/footer."""
    # Qt rich text lays tables out left-to-right, so columns are listed visually:
    # total (left) | qty | item (right).
    rows = []
    for it in sale.items:
        imei = f"<br/><span class='imei'>IMEI: {escape(it.device.imei1)}</span>" if it.device else ""
        rows.append(
            f"<tr><td width='30%' align='left'>{escape(format_money(it.line_total))}</td>"
            f"<td width='15%' align='center'>{it.quantity}</td>"
            f"<td width='55%' align='right'>{escape(it.product.name)}{imei}</td></tr>"
        )

    def total_row(label: str, value: int, strong: bool = False) -> str:
        cls = " class='strong'" if strong else ""
        return (f"<tr{cls}><td width='30%' align='left'>{escape(format_money(value))}</td>"
                f"<td colspan='2' align='right'>{escape(label)}</td></tr>")

    totals = [total_row(ar.RECEIPT_SUBTOTAL, sale.subtotal)]
    if sale.discount > 0:
        totals.append(total_row(ar.RECEIPT_DISCOUNT, sale.discount))
    totals.append(total_row(ar.RECEIPT_NET, sale.total, strong=True))
    totals.append(total_row(ar.RECEIPT_PAID, sale.paid))
    if sale.remaining > 0:
        totals.append(total_row(ar.RECEIPT_REMAINING, sale.remaining, strong=True))

    contact = " | ".join(x for x in (cfg.get("shop_address", ""), cfg.get("shop_phone", "")) if x)
    customer = sale.customer.name if sale.customer else "عميل نقدي"
    cashier = sale.user.full_name if sale.user else "—"
    date = clock.fmt_local(sale.created_at, "%Y-%m-%d %H:%M")

    return f"""
<html><head><style>
 body {{ font-family: 'Cairo'; font-size: 9pt; color: #000; }}
 h1 {{ font-size: 13pt; text-align: center; margin: 0; }}
 .sub {{ text-align: center; font-size: 8pt; margin: 0; }}
 table {{ width: 100%; border-collapse: collapse; }}
 th {{ border-bottom: 1px solid #000; font-size: 8.5pt; }}
 td {{ padding: 2px 0; vertical-align: top; }}
 .item {{ text-align: right; }} .c {{ text-align: center; }} .n {{ text-align: left; white-space: nowrap; }}
 .imei {{ font-size: 7.5pt; }} .strong td {{ font-weight: bold; border-top: 1px solid #000; }}
 hr {{ border: 0; border-top: 1px dashed #000; }} .foot {{ text-align: center; font-size: 8pt; }}
</style></head><body dir="rtl">
<h1>{escape(cfg.get('shop_name', ''))}</h1>
{f"<p class='sub'>{escape(contact)}</p>" if contact else ""}
<p class="sub"><b>{escape(ar.RECEIPT_TITLE)}</b></p>
<hr/>
<div>{escape(ar.SALE_DONE_INVOICE)}: {escape(sale.invoice_no)}<br/>
{escape(ar.RECEIPT_DATE)}: ⁦{escape(date)}⁩<br/>
{escape(ar.RECEIPT_CASHIER)}: {escape(cashier)}<br/>{escape(ar.RECEIPT_CUSTOMER)}: {escape(customer)}</div>
<hr/>
<table width="100%" cellspacing="0">
<tr><th width="30%" align="left">{escape(ar.RECEIPT_COL_TOTAL)}</th><th width="15%" align="center">{escape(ar.RECEIPT_COL_QTY)}</th><th width="55%" align="right">{escape(ar.RECEIPT_COL_ITEM)}</th></tr>
{''.join(rows)}
</table>
<hr/>
<table width="100%" cellspacing="0">{''.join(totals)}</table>
<hr/>
<p class="foot">{escape(cfg.get('invoice_footer', ''))}<br/>{escape(ar.RECEIPT_RETURN_POLICY)}</p>
</body></html>
"""
