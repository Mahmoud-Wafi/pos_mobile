"""Activation screen shown before login on a computer that has no valid licence."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from app.core import license as lic
from app.i18n import ar
from app.ui.components import show_error
from app.ui.design.style import set_prop, style_label


class ActivationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(ar.LIC_TITLE)
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)

        intro = QLabel(ar.LIC_INTRO)
        intro.setWordWrap(True)
        lay.addWidget(intro)

        lbl = QLabel(ar.LIC_MACHINE)
        style_label(lbl, bold=True)
        lay.addWidget(lbl)
        row = QHBoxLayout()
        self.machine_edit = QLineEdit(lic.machine_code())
        self.machine_edit.setReadOnly(True)
        self.machine_edit.setFixedHeight(40)
        self.machine_edit.setLayoutDirection(Qt.LeftToRight)
        self.btn_copy = QPushButton(ar.LIC_COPY)
        self.btn_copy.clicked.connect(self._copy)
        row.addWidget(self.machine_edit, 1)
        row.addWidget(self.btn_copy)
        lay.addLayout(row)

        lbl2 = QLabel(ar.LIC_CODE_LABEL)
        style_label(lbl2, bold=True)
        lay.addWidget(lbl2)
        self.code_edit = QPlainTextEdit()
        self.code_edit.setPlaceholderText(ar.LIC_CODE_PLACEHOLDER)
        self.code_edit.setFixedHeight(90)
        lay.addWidget(self.code_edit)

        btns = QHBoxLayout()
        self.btn_activate = QPushButton(ar.LIC_ACTIVATE)
        set_prop(self.btn_activate, "variant", "primary")
        self.btn_activate.setFixedHeight(40)
        self.btn_activate.clicked.connect(self._activate)
        self.btn_exit = QPushButton(ar.LIC_EXIT)
        self.btn_exit.setFixedHeight(40)
        self.btn_exit.clicked.connect(self.reject)
        btns.addWidget(self.btn_activate)
        btns.addWidget(self.btn_exit)
        lay.addLayout(btns)

    def _copy(self):
        QApplication.clipboard().setText(self.machine_edit.text())
        self.btn_copy.setText(ar.LIC_COPIED)

    def _activate(self):
        if lic.activate(self.code_edit.toPlainText()):
            self.accept()
        else:
            show_error(self, ar.LIC_BAD)
