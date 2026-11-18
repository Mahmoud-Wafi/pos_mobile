"""Modern Stocktake (physical inventory count) widget with clean card layout."""
from __future__ import annotations
from app.i18n import ar
from app.ui.components import show_error, show_toast
from app.ui.design.style import set_prop, style_label

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
        QSpinBox, QLineEdit, QFormLayout, QMessageBox, QLabel,
        QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QGridLayout,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    HAS_QT = True
except ImportError:
    HAS_QT = False

if HAS_QT:
    from app.services import inventory_service
    from app.models.product import Product
    from app.core.permissions import PermissionDenied

    class StocktakeWidget(QWidget):
        def __init__(self, session, user, parent=None):
            super().__init__(parent)
            self.session = session
            self.user = user
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(16)

            # Card 1: Input Form
            form_card = QFrame()
            set_prop(form_card, "card", True)
            form_layout = QVBoxLayout(form_card)

            card_title = QLabel(ar.STOCKTAKE_WIDGET_A628BE)
            style_label(card_title, size="title", tone="text", bold=True)
            card_sub = QLabel(ar.STOCKTAKE_WIDGET_D7A4DC)
            style_label(card_sub, size="caption", tone="muted")
            form_layout.addWidget(card_title)
            form_layout.addWidget(card_sub)

            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(10)

            lbl_prod = QLabel(ar.STOCKTAKE_WIDGET_1AC56E)
            style_label(lbl_prod, tone="text", bold=True)
            self.product_combo = QComboBox()
            self._load_products()

            lbl_actual = QLabel(ar.STOCKTAKE_WIDGET_22B850)
            style_label(lbl_actual, tone="text", bold=True)
            self.actual_qty = QSpinBox()
            self.actual_qty.setRange(0, 99999)
            self.actual_qty.setSuffix(ar.STOCKTAKE_WIDGET_C35BDF)

            lbl_reason = QLabel(ar.STOCKTAKE_WIDGET_F6C98C)
            style_label(lbl_reason, tone="text", bold=True)
            self.reason_edit = QLineEdit()
            self.reason_edit.setPlaceholderText(ar.STOCKTAKE_WIDGET_0FA5D5)

            grid.addWidget(lbl_prod, 0, 0)
            grid.addWidget(lbl_actual, 0, 1)
            grid.addWidget(lbl_reason, 0, 2)

            grid.addWidget(self.product_combo, 1, 0)
            grid.addWidget(self.actual_qty, 1, 1)
            grid.addWidget(self.reason_edit, 1, 2)

            form_layout.addLayout(grid)

            btn_box = QHBoxLayout()
            btn_box.addStretch()
            self.btn_submit = QPushButton(ar.STOCKTAKE_WIDGET_54E462)
            self.btn_submit.setProperty("class", "PrimaryBtn")
            self.btn_submit.setFixedWidth(180)
            self.btn_submit.clicked.connect(self._do_stocktake)
            btn_box.addWidget(self.btn_submit)

            form_layout.addLayout(btn_box)
            layout.addWidget(form_card)

            # Card 2: History Table
            history_title = QLabel(ar.STOCKTAKE_WIDGET_4BCE15)
            style_label(history_title, size="label", tone="text", bold=True)
            layout.addWidget(history_title)

            self.history_table = QTableWidget()
            self.history_table.setColumnCount(4)
            self.history_table.setHorizontalHeaderLabels([ar.STOCKTAKE_WIDGET_FA4E1F, ar.STOCKTAKE_WIDGET_2A169F, ar.STOCKTAKE_WIDGET_4F7006, ar.STOCKTAKE_WIDGET_514A6A])
            self.history_table.verticalHeader().setVisible(False)
            self.history_table.verticalHeader().setDefaultSectionSize(40)
            self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed); self.history_table.setColumnWidth(1, 140)
            self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed); self.history_table.setColumnWidth(3, 170)
            self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.history_table.setAlternatingRowColors(True)

            layout.addWidget(self.history_table)
            self._load_history()

        def _load_products(self):
            self.product_combo.clear()
            self._products = self.session.query(Product).filter(
                Product.track_imei == False, Product.is_active == True
            ).order_by(Product.name).all()
            for p in self._products:
                qty = p.current_quantity()
                self.product_combo.addItem(f"{p.name}  (الرصيد بالدفتر: {qty})", p)

        def _do_stocktake(self):
            if not self._products:
                show_error(self, message=ar.STOCKTAKE_WIDGET_5F986A)
                return
            product = self.product_combo.currentData()
            actual = self.actual_qty.value()
            reason = self.reason_edit.text().strip() or ar.STOCKTAKE_WIDGET_657678
            try:
                mv = inventory_service.stocktake(self.session, self.user, product, actual, reason)
                self.session.commit()
                if mv is None:
                    QMessageBox.information(self, ar.STOCKTAKE_WIDGET_BFECD1, ar.STOCKTAKE_WIDGET_85CCAA)
                else:
                    sign = "+" if mv.quantity > 0 else ""
                    show_toast(self, f"تم اعتماد الجرد وتسجيل حركة تسوية: {sign}{mv.quantity} قطعة")
                self._load_products()
                self._load_history()
            except PermissionDenied as e:
                show_error(self, e)
            except Exception as e:
                self.session.rollback()
                show_error(self, e)

        def _load_history(self):
            from app.models.stock import StockMovement
            movements = self.session.query(StockMovement).filter(
                StockMovement.type == "adjust"
            ).order_by(StockMovement.created_at.desc()).limit(50).all()
            self.history_table.setRowCount(len(movements))
            for row, mv in enumerate(movements):
                diff_text = f"{mv.quantity:+d} قطعة"
                diff_color = "#059669" if mv.quantity > 0 else "#DC2626"

                items = [
                    (mv.product.name if mv.product else str(mv.product_id), Qt.AlignRight | Qt.AlignVCenter, None, True),
                    (diff_text, Qt.AlignCenter, diff_color, True),
                    (mv.note or "—", Qt.AlignRight | Qt.AlignVCenter, "#64748B", False),
                    (mv.created_at.strftime("%Y-%m-%d  %I:%M %p") if mv.created_at else "", Qt.AlignCenter, "#334155", False),
                ]

                for col, (text, align, fg, is_bold) in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(align)
                    item.setForeground(QColor(fg or "#0F172A"))
                    if is_bold:
                        f = item.font(); f.setBold(True); item.setFont(f)
                    self.history_table.setItem(row, col, item)
