"""Close-shift dialog with a blind cash count."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from app.core.money import format_money, parse_egp_input
from app.i18n import ar
from app.services import shift_service


class CloseShiftDialog(QDialog):
    """Step 1: cashier enters the counted cash (expected amount hidden).
    Step 2: after confirming, expected / actual / difference are shown.
    """

    def __init__(self, session, user, shift, parent=None):
        super().__init__(parent)
        self.session, self.user, self.shift = session, user, shift
        self.closed = False
        self.result_shift = None
        self.setWindowTitle(ar.SHIFT_CLOSE)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumWidth(440)
        self.setModal(True)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(24, 20, 24, 20)
        self.root.setSpacing(10)

        self.hint = QLabel(ar.SHIFT_CLOSE_BLIND_HINT)
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #475569;")
        self.root.addWidget(self.hint)

        self.form = QFormLayout()
        self.actual_edit = QLineEdit()
        self.actual_edit.setMinimumHeight(40)
        self.notes_edit = QLineEdit()
        self.form.addRow(ar.SHIFT_ACTUAL_CASH, self.actual_edit)
        self.form.addRow(ar.SHIFT_NOTES, self.notes_edit)
        self.root.addLayout(self.form)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #DC2626; font-weight: 600;")
        self.root.addWidget(self.error_lbl)

        self.btn = QPushButton(ar.SHIFT_CONFIRM_CLOSE)
        self.btn.setObjectName("DangerBtn")
        self.btn.setMinimumHeight(42)
        self.btn.clicked.connect(self.confirm)
        self.root.addWidget(self.btn)
        self.actual_edit.returnPressed.connect(self.confirm)
        self.actual_edit.setFocus()

    def confirm(self) -> None:
        if self.closed:
            self.accept()
            return
        try:
            actual = parse_egp_input(self.actual_edit.text())
        except ValueError:
            self.error_lbl.setText(ar.SHIFT_INVALID_AMOUNT)
            return
        try:
            self.result_shift = shift_service.close_shift(
                self.session, self.user, self.shift.id, actual, notes=self.notes_edit.text().strip() or None)
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            self.error_lbl.setText(str(exc))
            return
        self.closed = True
        self._show_result()

    def _show_result(self) -> None:
        sh = self.result_shift
        self.hint.setText(ar.SHIFT_RESULT_TITLE)
        self.hint.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")
        self.error_lbl.setText("")
        for w in (self.actual_edit, self.notes_edit):
            w.setEnabled(False)
        diff = sh.diff
        if diff == 0:
            verdict, color = ar.SHIFT_BALANCED, "#059669"
        elif diff > 0:
            verdict, color = f"{ar.SHIFT_SURPLUS}: {format_money(diff)}", "#0284C7"
        else:
            verdict, color = f"{ar.SHIFT_SHORTAGE}: {format_money(-diff)}", "#DC2626"
        self.result_lbl = QLabel(
            f"{ar.SHIFT_EXPECTED}: {format_money(sh.expected_cash)}\n"
            f"{ar.SHIFT_ACTUAL}: {format_money(sh.actual_cash)}\n{verdict}")
        self.result_lbl.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {color};")
        self.root.insertWidget(1, self.result_lbl)
        self.btn.setText(ar.CLOSE)
        self.btn.setObjectName("PrimaryBtn")
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)
