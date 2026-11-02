"""Returns & Warranty Lookup Window."""
from __future__ import annotations

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

from app.core.money import format_money
from app.services import sales_service


HEADERS = ["رقم الفاتورة", "اسم العميل", "الصنف / الموديل", "السيريال (IMEI)", "حالة الضمان", "الأيام المتبقية", "تاريخ انتهاء الضمان", "إجراء"]


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
            search_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px;")
            s_layout = QVBoxLayout(search_card)

            title = QLabel("🔍 استعلام عن الضمان ومرتجعات المبيعات")
            title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0F172A;")
            sub = QLabel("ابحث برقم السيريال (IMEI) أو رقم الفاتورة أو هاتف العميل لفحص سريان الضمان أو تسجيل مرتجع")
            sub.setStyleSheet("font-size: 12px; color: #64748B;")
            s_layout.addWidget(title)
            s_layout.addWidget(sub)

            bar = QHBoxLayout()
            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText("اكتب رقم السيريال (IMEI) أو رقم الفاتورة (INV-...) واضغط Enter...")
            self.search_edit.setFixedHeight(44)
            self.search_edit.returnPressed.connect(self._do_search)
            bar.addWidget(self.search_edit)

            btn_search = QPushButton("🔍 بحث")
            btn_search.setFixedHeight(44)
            btn_search.setMinimumWidth(100)
            btn_search.setObjectName("PrimaryBtn")
            btn_search.clicked.connect(self._do_search)
            bar.addWidget(btn_search)

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

            layout.addWidget(self.table)

        def _do_search(self):
            q = self.search_edit.text().strip()
            if not q:
                return

            self.session.expire_all()
            results = sales_service.search_warranty(self.session, q)
            self.table.setRowCount(len(results))

            if not results:
                QMessageBox.information(self, "نتيجة البحث", "لم يتم العثور على أي فاتورة أو جهاز يطابق هذا البحث")
                return

            for row, r in enumerate(results):
                status_text = "ساري ومفعل ✓" if r["is_valid"] else "منتهي الصلاحية ✕"
                bg_color = "#ECFDF5" if r["is_valid"] else "#FEE2E2"
                fg_color = "#065F46" if r["is_valid"] else "#991B1B"
                end_str = r["warranty_end_date"].strftime("%Y-%m-%d") if r["warranty_end_date"] else "بدون ضمان"

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
                btn_return = QPushButton("↩️ مرتجع")
                btn_return.setStyleSheet("background-color: #FEF3C7; color: #92400E; font-weight: bold; border: 1px solid #FCD34D; border-radius: 6px;")
                s_item_id = r["sale_item_id"]
                btn_return.clicked.connect(lambda _, sid=s_item_id: self._process_return(sid))
                self.table.setCellWidget(row, 7, btn_return)

        def _process_return(self, sale_item_id: int):
            reason, ok = QInputDialog.getText(self, "تسجيل مرتجع", "سبب إرجاع الصنف:")
            if not (ok and reason.strip()):
                return

            from app.models.sale import SaleItem
            sale_item = self.session.get(SaleItem, sale_item_id)
            if not sale_item:
                return

            reply = QMessageBox.question(
                self, "إعادة للمخزن",
                "هل الصنف بحالة جيدة ويصلح لإعادة إدخاله للمخزن وبيعه مرة أخرى؟",
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
                QMessageBox.information(
                    self, "تم المرتجع بنجاح ✓",
                    f"تم تسجيل إشعار مرتجع #{ret.return_no}\nقيمة المبلغ المردود: {format_money(ret.refund_amount)}"
                )
                self._do_search()
            except Exception as e:
                self.session.rollback()
                QMessageBox.critical(self, "خطأ في تسجيل المرتجع", str(e))

