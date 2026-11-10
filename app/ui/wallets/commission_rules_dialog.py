"""Dialog for viewing and editing data-driven commission rules for mobile wallets."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFrame, QGroupBox, QGridLayout,
)

from decimal import Decimal
from app.core.money import parse_egp_input, parse_percent_to_bp
from app.core.money import egp_to_piasters, format_money, piasters_to_egp
from app.core.money import piasters_to_input
from app.models.wallet import CommissionRule
from app.services import wallet_service


class CommissionRulesDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.setWindowTitle("قواعد ونسب العمولات للمحافظ الإلكترونية")
        self.resize(850, 580)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #F8FAFC;
            }
            QLabel {
                color: #0F172A;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit, QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                color: #0F172A;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #2563EB;
            }
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            QHeaderView::section {
                background-color: #F1F5F9;
                color: #334155;
                font-weight: bold;
                padding: 8px;
                border: none;
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        self._build_ui()
        self.load_rules()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel("⚙️")
        icon.setStyleSheet("font-size: 26px;")
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel("قواعد حساب عمولات العمليات (إيداع، سحب، فواتير)")
        lbl_t.setStyleSheet("font-size: 17px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("يتم احتساب العمولة تلقائياً عند إدخال المبلغ بناءً على هذه الشرائح")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; font-weight: normal;")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Add Rule Quick Bar
        add_box = QFrame()
        add_box.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;")
        add_grid = QGridLayout(add_box)
        add_grid.setHorizontalSpacing(10)
        add_grid.setVerticalSpacing(6)

        add_grid.addWidget(QLabel("الشبكة:"), 0, 0)
        self.net_combo = QComboBox()
        self.net_combo.addItem("فودافون", "vodafone")
        self.net_combo.addItem("أورنج", "orange")
        self.net_combo.addItem("اتصالات", "etisalat")
        self.net_combo.addItem("إنستاباي", "instapay")
        add_grid.addWidget(self.net_combo, 1, 0)

        add_grid.addWidget(QLabel("نوع العملية:"), 0, 1)
        self.op_combo = QComboBox()
        self.op_combo.addItem("إيداع (Cash In)", "cash_in")
        self.op_combo.addItem("سحب (Cash Out)", "cash_out")
        self.op_combo.addItem("فواتير (Bill)", "bill")
        self.op_combo.addItem("شحن (Recharge)", "recharge")
        add_grid.addWidget(self.op_combo, 1, 1)

        add_grid.addWidget(QLabel("الحد الأدنى (ج.م):"), 0, 2)
        self.min_edit = QLineEdit("1.00")
        self.min_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        add_grid.addWidget(self.min_edit, 1, 2)

        add_grid.addWidget(QLabel("الحد الأقصى (ج.م):"), 0, 3)
        self.max_edit = QLineEdit("5000.00")
        self.max_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        add_grid.addWidget(self.max_edit, 1, 3)

        add_grid.addWidget(QLabel("عمولة ثابتة (ج.م):"), 0, 4)
        self.fix_edit = QLineEdit("5.00")
        self.fix_edit.setValidator(QDoubleValidator(0.0, 9999.0, 2))
        add_grid.addWidget(self.fix_edit, 1, 4)

        add_grid.addWidget(QLabel("نسبة %:"), 0, 5)
        self.pct_edit = QLineEdit("0.0")
        self.pct_edit.setValidator(QDoubleValidator(0.0, 100.0, 2))
        add_grid.addWidget(self.pct_edit, 1, 5)

        btn_add = QPushButton("➕ إضافة قاعدة")
        btn_add.setFixedHeight(36)
        btn_add.setStyleSheet("background-color: #2563EB; color: white; border-radius: 6px; font-weight: bold; padding: 0 14px;")
        btn_add.clicked.connect(self._add_rule)
        add_grid.addWidget(btn_add, 1, 6)

        layout.addWidget(add_box)

        # Rules Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "#", "الشبكة", "العملية", "من مبلغ", "إلى مبلغ", "العمولة الثابتة", "النسبة %", "المسدد"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed); self.table.setColumnWidth(0, 40)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.Fixed); self.table.setColumnWidth(3, 110)
        h.setSectionResizeMode(4, QHeaderView.Fixed); self.table.setColumnWidth(4, 110)
        h.setSectionResizeMode(5, QHeaderView.Fixed); self.table.setColumnWidth(5, 110)
        h.setSectionResizeMode(6, QHeaderView.Fixed); self.table.setColumnWidth(6, 90)
        h.setSectionResizeMode(7, QHeaderView.Fixed); self.table.setColumnWidth(7, 90)
        layout.addWidget(self.table)

        btn_close = QPushButton("إغلاق")
        btn_close.setFixedHeight(40)
        btn_close.setStyleSheet("background-color: #F1F5F9; color: #475569; border: 1px solid #CBD5E1; border-radius: 8px; font-weight: bold;")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def load_rules(self):
        rules = wallet_service.list_commission_rules(self.session, self.user)
        self.table.setRowCount(len(rules))
        for idx, r in enumerate(rules):
            self.table.setItem(idx, 0, QTableWidgetItem(str(r.id)))
            self.table.setItem(idx, 1, QTableWidgetItem(r.network.title()))
            self.table.setItem(idx, 2, QTableWidgetItem(r.op_type))
            self.table.setItem(idx, 3, QTableWidgetItem(format_money(r.min_amount)))
            self.table.setItem(idx, 4, QTableWidgetItem(format_money(r.max_amount) if r.max_amount else "بلا سقف"))
            self.table.setItem(idx, 5, QTableWidgetItem(format_money(r.fixed_fee)))
            pct_val = f"{piasters_to_input(r.percent_bp)}%"
            self.table.setItem(idx, 6, QTableWidgetItem(pct_val))
            self.table.setItem(idx, 7, QTableWidgetItem("العميل" if r.paid_by == "customer" else "الشبكة"))

    def _add_rule(self):
        try:
            net = self.net_combo.currentData()
            op = self.op_combo.currentData()
            min_amt = parse_egp_input(self.min_edit.text() or '0')
            max_amt = parse_egp_input(self.max_edit.text() or '0')
            fixed_fee = parse_egp_input(self.fix_edit.text() or '0')
            percent_bp = parse_percent_to_bp(self.pct_edit.text())

            wallet_service.create_commission_rule(
                self.session, self.user,
                network=net, op_type=op, min_amount=min_amt, max_amount=max_amt,
                fixed_fee=fixed_fee, percent_bp=percent_bp,
            )
            self.session.commit()
            self.load_rules()
            QMessageBox.information(self, "نجاح", "تم حفظ قاعدة العمولة بنجاح!")
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر إضافة القاعدة:\n{str(e)}")

