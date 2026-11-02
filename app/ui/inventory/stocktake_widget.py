"""Modern Stocktake (physical inventory count) widget with clean card layout."""
from __future__ import annotations

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
            form_card.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 10px; padding: 16px;")
            form_layout = QVBoxLayout(form_card)

            card_title = QLabel("📋 تسجيل الجرد الفعلي للمخزون")
            card_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #0F172A;")
            card_sub = QLabel("اختر الصنف وأدخل الكمية الفعلية الموجودة في المحل لتسجيل حركة تسوية آلية")
            card_sub.setStyleSheet("font-size: 12px; color: #64748B; margin-bottom: 8px;")
            form_layout.addWidget(card_title)
            form_layout.addWidget(card_sub)

            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(10)

            lbl_prod = QLabel("الصنف المراد جرده *")
            lbl_prod.setStyleSheet("font-weight: 600; color: #334155;")
            self.product_combo = QComboBox()
            self._load_products()

            lbl_actual = QLabel("الكمية الفعلية الموجودة *")
            lbl_actual.setStyleSheet("font-weight: 600; color: #334155;")
            self.actual_qty = QSpinBox()
            self.actual_qty.setRange(0, 99999)
            self.actual_qty.setSuffix(" قطعة")

            lbl_reason = QLabel("سبب أو بيان الجرد")
            lbl_reason.setStyleSheet("font-weight: 600; color: #334155;")
            self.reason_edit = QLineEdit()
            self.reason_edit.setPlaceholderText("مثال: جرد نهاية الشهر، تسوية عجز...")

            grid.addWidget(lbl_prod, 0, 0)
            grid.addWidget(lbl_actual, 0, 1)
            grid.addWidget(lbl_reason, 0, 2)

            grid.addWidget(self.product_combo, 1, 0)
            grid.addWidget(self.actual_qty, 1, 1)
            grid.addWidget(self.reason_edit, 1, 2)

            form_layout.addLayout(grid)

            btn_box = QHBoxLayout()
            btn_box.addStretch()
            self.btn_submit = QPushButton("💾 اعتماد وتسجيل الجرد")
            self.btn_submit.setProperty("class", "PrimaryBtn")
            self.btn_submit.setFixedWidth(180)
            self.btn_submit.clicked.connect(self._do_stocktake)
            btn_box.addWidget(self.btn_submit)

            form_layout.addLayout(btn_box)
            layout.addWidget(form_card)

            # Card 2: History Table
            history_title = QLabel("📜 سجل حركات التسوية والجرد الأخيرة:")
            history_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0F172A;")
            layout.addWidget(history_title)

            self.history_table = QTableWidget()
            self.history_table.setColumnCount(4)
            self.history_table.setHorizontalHeaderLabels(["اسم الصنف", "فرق التسوية", "البيان / السبب", "تاريخ ووقت الجرد"])
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
                QMessageBox.warning(self, "تنبيه", "لا توجد منتجات غير IMEI للجرد")
                return
            product = self.product_combo.currentData()
            actual = self.actual_qty.value()
            reason = self.reason_edit.text().strip() or "جرد دوري للمخزن"
            try:
                mv = inventory_service.stocktake(self.session, self.user, product, actual, reason)
                self.session.commit()
                if mv is None:
                    QMessageBox.information(self, "معلومة", "الكمية الفعلية مطابقة لرصيد السيستم — لم يتطلب أي تسوية.")
                else:
                    sign = "+" if mv.quantity > 0 else ""
                    QMessageBox.information(self, "تم بنجاح", f"تم اعتماد الجرد وتسجيل حركة تسوية: {sign}{mv.quantity} قطعة")
                self._load_products()
                self._load_history()
            except PermissionDenied as e:
                QMessageBox.critical(self, "خطأ في الصلاحية", str(e))
            except Exception as e:
                self.session.rollback()
                QMessageBox.critical(self, "خطأ", str(e))

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
