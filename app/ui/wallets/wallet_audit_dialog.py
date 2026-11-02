"""Dialog for performing physical vs recorded wallet audit at shift or day close."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFrame,
)

from app.core.money import egp_to_piasters, format_money
from app.models.wallet import Wallet
from app.services import wallet_service


class WalletAuditDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session = session
        self.user = user
        self.setWindowTitle("جرد وتدقيق رصيد المحفظة (Audit)")
        self.resize(480, 420)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background-color: #FFFFFF;
            }
            QLabel {
                color: #0F172A;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit, QComboBox {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
                color: #0F172A;
            }
            QLineEdit:focus, QComboBox:focus {
                background-color: #FFFFFF;
                border: 2px solid #2563EB;
            }
        """)
        self._build_ui()
        self._load_wallets()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Header
        hdr = QHBoxLayout()
        icon = QLabel("⚖️")
        icon.setStyleSheet("font-size: 28px;")
        hdr.addWidget(icon)

        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        lbl_t = QLabel("مطابقة الرصيد الدفتري والفعلي للمحفظة")
        lbl_t.setStyleSheet("font-size: 16px; font-weight: bold; color: #0F172A;")
        lbl_sub = QLabel("مقارنة رصيد السيستم مع رسالة الرصيد الفعلي من الشبكة وتسجيل الفروقات")
        lbl_sub.setStyleSheet("font-size: 12px; color: #64748B; font-weight: normal;")
        t_box.addWidget(lbl_t)
        t_box.addWidget(lbl_sub)
        hdr.addLayout(t_box)
        hdr.addStretch()
        layout.addLayout(hdr)

        # Select Wallet
        layout.addWidget(QLabel("اختر المحفظة المراد جردها: *"))
        self.wallet_combo = QComboBox()
        self.wallet_combo.setFixedHeight(42)
        self.wallet_combo.currentIndexChanged.connect(self._on_wallet_changed)
        layout.addWidget(self.wallet_combo)

        # Current System Balance Card
        card = QFrame()
        card.setStyleSheet("background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 8px; padding: 12px;")
        c_layout = QHBoxLayout(card)
        c_title = QLabel("الرصيد الدفتري المسجل بالسيستم:")
        c_title.setStyleSheet("color: #1E3A8A; font-weight: bold;")
        self.lbl_sys_bal = QLabel("0.00 ج.م")
        self.lbl_sys_bal.setStyleSheet("color: #1D4ED8; font-weight: bold; font-size: 16px;")
        c_layout.addWidget(c_title)
        c_layout.addStretch()
        c_layout.addWidget(self.lbl_sys_bal)
        layout.addWidget(card)

        # Actual Balance Input
        layout.addWidget(QLabel("الرصيد الفعلي بالخط الآن (ج.م): *"))
        self.actual_edit = QLineEdit()
        self.actual_edit.setFixedHeight(42)
        self.actual_edit.setPlaceholderText("0.00 ج.م (كما يظهر برسالة كود الاستعلام)")
        self.actual_edit.setValidator(QDoubleValidator(0.0, 9999999.0, 2))
        self.actual_edit.textChanged.connect(self._recalc_diff)
        layout.addWidget(self.actual_edit)

        # Diff Card
        self.diff_card = QFrame()
        self.diff_card.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;")
        d_layout = QHBoxLayout(self.diff_card)
        d_title = QLabel("فرق الجرد (عجز / زيادة):")
        d_title.setStyleSheet("font-weight: bold;")
        self.lbl_diff = QLabel("0.00 ج.م")
        self.lbl_diff.setStyleSheet("font-weight: bold; font-size: 16px; color: #16A34A;")
        d_layout.addWidget(d_title)
        d_layout.addStretch()
        d_layout.addWidget(self.lbl_diff)
        layout.addWidget(self.diff_card)

        # Note
        layout.addWidget(QLabel("ملاحظات الجرد:"))
        self.note_edit = QLineEdit()
        self.note_edit.setFixedHeight(40)
        self.note_edit.setPlaceholderText("سبب العجز أو الزيادة إن وجد...")
        layout.addWidget(self.note_edit)

        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(12)

        btn_cancel = QPushButton("إلغاء")
        btn_cancel.setFixedHeight(42)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                font-weight: 600;
                padding: 0 18px;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("💾 اعتماد وتسجيل الجرد")
        btn_save.setFixedHeight(42)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: white;
                border-radius: 8px;
                font-weight: bold;
                padding: 0 24px;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        btn_save.clicked.connect(self._save_audit)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _load_wallets(self):
        self.wallet_combo.clear()
        wallets = wallet_service.list_wallets(self.session, self.user, active_only=True)
        for w in wallets:
            self.wallet_combo.addItem(f"{w.label} - {w.phone_number}", w)

    def _on_wallet_changed(self):
        w: Optional[Wallet] = self.wallet_combo.currentData()
        if w:
            self.lbl_sys_bal.setText(format_money(w.balance))
            self._recalc_diff()

    def _recalc_diff(self):
        w: Optional[Wallet] = self.wallet_combo.currentData()
        if not w:
            return
        actual_str = self.actual_edit.text().strip()
        try:
            actual_piasters = egp_to_piasters(actual_str) if actual_str else w.balance
        except Exception:
            actual_piasters = w.balance

        diff_piasters = actual_piasters - w.balance
        self.lbl_diff.setText(format_money(diff_piasters))
        if diff_piasters < 0:
            self.lbl_diff.setStyleSheet("font-weight: bold; font-size: 16px; color: #DC2626;")
        elif diff_piasters > 0:
            self.lbl_diff.setStyleSheet("font-weight: bold; font-size: 16px; color: #2563EB;")
        else:
            self.lbl_diff.setStyleSheet("font-weight: bold; font-size: 16px; color: #16A34A;")

    def _save_audit(self):
        w: Optional[Wallet] = self.wallet_combo.currentData()
        if not w:
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار المحفظة")
            return

        actual_str = self.actual_edit.text().strip()
        if not actual_str:
            QMessageBox.warning(self, "تنبيه", "يرجى كتابة الرصيد الفعلي المستعلم عنه")
            self.actual_edit.setFocus()
            return

        try:
            actual_piasters = egp_to_piasters(actual_str)
        except Exception:
            QMessageBox.warning(self, "تنبيه", "صيغة الرصيد الفعلي غير صحيحة")
            return

        note = self.note_edit.text().strip()

        try:
            audit = wallet_service.audit_wallet(
                self.session, self.user,
                wallet_id=w.id,
                actual_balance=actual_piasters,
                note=note,
            )
            self.session.commit()
            QMessageBox.information(
                self,
                "تم تسجيل الجرد",
                f"تم تدقيق وجرد المحفظة بنجاح.\nفرق الجرد: {format_money(audit.diff)}"
            )
            self.accept()
        except Exception as e:
            self.session.rollback()
            QMessageBox.critical(self, "خطأ", f"تعذر تسجيل الجرد:\n{str(e)}")

