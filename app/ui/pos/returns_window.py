"""Returns & Warranty Lookup Window."""
from __future__ import annotations
from app.i18n import ar

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
        QTableWidgetItem, QHeaderView, QLabel, QLineEdit,
        QMessageBox, QFrame, QInputDialog,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    HAS_QT = True
except ImportError:
    HAS_QT = False

from app.ui.components import show_error, show_toast
from app.core.money import format_money
from app.services import sales_service
from app.ui.design.style import set_prop, style_label, variant


HEADERS = [ar.SALE_DONE_INVOICE, ar.CUSTOMERS_WINDOW_2B9848, ar.RETURNS_WINDOW_C4F854, ar.COL_IMEI, ar.RETURNS_WINDOW_82D91A, ar.RETURNS_WINDOW_BFC686, ar.RETURNS_WINDOW_24B433, ar.RETURNS_WINDOW_155E71, ar.WARRANTY_OPEN_CLAIM]


if HAS_QT:
    class ReturnsWindow(QWidget):
        """Warranty search and invoice returns screen."""

        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(14)

            # Search Bar Card
            search_card = QFrame()
            set_prop(search_card, "card", True)
            s_layout = QVBoxLayout(search_card)

            title = QLabel(ar.RETURNS_WINDOW_C7C8CF)
            style_label(title, size="title", tone="text", bold=True)
            sub = QLabel(ar.RETURNS_WINDOW_B088E2)
            style_label(sub, size="caption", tone="muted")
            s_layout.addWidget(title)
            s_layout.addWidget(sub)

            bar = QHBoxLayout()
            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText(ar.RETURNS_WINDOW_9D4672)
            self.search_edit.setFixedHeight(44)
            self.search_edit.returnPressed.connect(self._do_search)
            bar.addWidget(self.search_edit)

            btn_search = QPushButton(ar.SEARCH)
            btn_search.setFixedHeight(44)
            btn_search.setMinimumWidth(100)
            btn_search.setObjectName("PrimaryBtn")
            btn_search.clicked.connect(self._do_search)
            bar.addWidget(btn_search)

            self.btn_claims = QPushButton(ar.WARRANTY_CLAIMS_TITLE)
            self.btn_claims.setFixedHeight(44)
            self.btn_claims.clicked.connect(self._show_claims)
            bar.addWidget(self.btn_claims)

            s_layout.addLayout(bar)
            layout.addWidget(search_card)

            # Results Table
            self.table = QTableWidget()
            self.table.setColumnCount(len(HEADERS))
            self.table.setHorizontalHeaderLabels(HEADERS)
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setDefaultSectionSize(46)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setAlternatingRowColors(True)

            header = self.table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed); self.table.setColumnWidth(0, 160) # Invoice
            header.setSectionResizeMode(1, QHeaderView.Fixed); self.table.setColumnWidth(1, 140) # Cust
            header.setSectionResizeMode(2, QHeaderView.Stretch)                                   # Prod
            header.setSectionResizeMode(3, QHeaderView.Fixed); self.table.setColumnWidth(3, 170) # IMEI
            header.setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 120) # Status
            header.setSectionResizeMode(5, QHeaderView.Fixed); self.table.setColumnWidth(5, 110) # Days
            header.setSectionResizeMode(6, QHeaderView.Fixed); self.table.setColumnWidth(6, 140) # Date
            header.setSectionResizeMode(7, QHeaderView.Fixed); self.table.setColumnWidth(7, 120) # Action
            header.setSectionResizeMode(8, QHeaderView.Fixed); self.table.setColumnWidth(8, 130) # Claim

            layout.addWidget(self.table)

        def _do_search(self):
            q = self.search_edit.text().strip()
            if not q:
                return

            self.session.expire_all()
            results = sales_service.search_warranty(self.session, q)
            self.table.setRowCount(len(results))

            if not results:
                QMessageBox.information(self, ar.RETURNS_WINDOW_548487, ar.RETURNS_WINDOW_314F43)
                return

            for row, r in enumerate(results):
                status_text = ar.RETURNS_WINDOW_AD12C7 if r["is_valid"] else ar.RETURNS_WINDOW_2E7E5D
                bg_color = "#ECFDF5" if r["is_valid"] else "#FEE2E2"
                fg_color = "#065F46" if r["is_valid"] else "#991B1B"
                end_str = r["warranty_end_date"].strftime("%Y-%m-%d") if r["warranty_end_date"] else ar.RETURNS_WINDOW_B7E4F8

                cols = [
                    (r["invoice_no"], Qt.AlignCenter),
                    (r["customer_name"], Qt.AlignCenter),
                    (r["product_name"], Qt.AlignRight | Qt.AlignVCenter),
                    (r["imei"], Qt.AlignCenter),
                    (status_text, Qt.AlignCenter),
                    (f"{r['days_left']} يوم" if r["is_valid"] else "0", Qt.AlignCenter),
                    (end_str, Qt.AlignCenter),
                ]

                for col, (text, align) in enumerate(cols):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(align)
                    if col == 4:
                        item.setBackground(QColor(bg_color))
                        item.setForeground(QColor(fg_color))
                        f = item.font(); f.setBold(True); item.setFont(f)
                    self.table.setItem(row, col, item)

                # Return action button
                btn_return = QPushButton(ar.HISTORY_RETURN)
                variant(btn_return, "secondary")
                s_item_id = r["sale_item_id"]
                btn_return.clicked.connect(lambda _, sid=s_item_id: self._process_return(sid))
                self.table.setCellWidget(row, 7, btn_return)

                btn_claim = QPushButton(ar.WARRANTY_OPEN_CLAIM)
                variant(btn_claim, "secondary")
                btn_claim.clicked.connect(lambda _, sid=s_item_id, ok=r["is_valid"]: self._open_claim(sid, ok))
                self.table.setCellWidget(row, 8, btn_claim)

        def _show_claims(self):
            from app.ui.pos.warranty_claims_dialog import WarrantyClaimsDialog

            WarrantyClaimsDialog(self.session, self.user, self).exec()

        def _open_claim(self, sale_item_id: int, in_warranty: bool):
            from app.services import warranty_service

            issue, ok = QInputDialog.getMultiLineText(
                self, ar.WARRANTY_OPEN_CLAIM, ar.WARRANTY_ISSUE_PROMPT + ("" if in_warranty else f"\n({ar.WARRANTY_OUT_NOTE})"))
            if not ok:
                return
            try:
                warranty_service.open_claim(self.session, self.user, sale_item_id, issue)
                self.session.commit()
            except Exception as e:
                self.session.rollback()
                show_error(self, e)
                return
            show_toast(self, ar.WARRANTY_CLAIM_OPENED)

        def _process_return(self, sale_item_id: int):
            reason, ok = QInputDialog.getText(self, ar.RETURNS_WINDOW_E04EEC, ar.RETURNS_WINDOW_FF5F3B)
            if not (ok and reason.strip()):
                return

            from app.models.sale import SaleItem
            sale_item = self.session.get(SaleItem, sale_item_id)
            if not sale_item:
                return

            reply = QMessageBox.question(
                self, ar.RETURNS_WINDOW_4C58AD,
                ar.RETURNS_WINDOW_63CB57,
                QMessageBox.Yes | QMessageBox.No
            )
            restock = (reply == QMessageBox.Yes)

            try:
                ret = sales_service.return_sale_items(
                    self.session, self.user, sale_item.sale_id,
                    return_items_data=[{"sale_item_id": sale_item.id, "quantity": 1}],
                    reason=reason.strip(),
                    restock=restock,
                    refund_method="cash",
                )
                self.session.commit()
                show_toast(self, f"تم تسجيل إشعار مرتجع #{ret.return_no}\nقيمة المبلغ المردود: {format_money(ret.refund_amount)}")
                self._do_search()
            except Exception as e:
                self.session.rollback()
                show_error(self, e)

