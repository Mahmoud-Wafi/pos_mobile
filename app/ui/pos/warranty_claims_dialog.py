"""Warranty claims list: see every case and move it through repair to a resolution."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QInputDialog, QLabel, QPushButton,
                               QVBoxLayout)

from app.core import clock
from app.i18n import ar
from app.services import warranty_service
from app.ui.components import DataTable, show_error, show_toast

STATUS_AR = {"open": ar.WARRANTY_STATUS_OPEN, "in_repair": ar.WARRANTY_STATUS_IN_REPAIR,
             "resolved": ar.WARRANTY_STATUS_RESOLVED, "rejected": ar.WARRANTY_STATUS_REJECTED}


class WarrantyClaimsDialog(QDialog):
    def __init__(self, session, user, parent=None):
        super().__init__(parent)
        self.session, self.user = session, user
        self._claims = []
        self.setWindowTitle(ar.WARRANTY_CLAIMS_TITLE)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(760, 440)
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel(ar.WARRANTY_COL_STATUS))
        self.filter = QComboBox()
        self.filter.addItem("—", None)
        for code, text in STATUS_AR.items():
            self.filter.addItem(text, code)
        self.filter.currentIndexChanged.connect(self.reload)
        bar.addWidget(self.filter)
        bar.addStretch()
        self.btn_status = QPushButton(ar.WARRANTY_SET_STATUS)
        self.btn_status.clicked.connect(self._change_status)
        bar.addWidget(self.btn_status)
        lay.addLayout(bar)
        self.table = DataTable([ar.SALE_DONE_INVOICE, ar.RETURNS_WINDOW_C4F854, ar.WARRANTY_COL_ISSUE,
                                ar.WARRANTY_COL_STATUS, ar.WARRANTY_COL_IN, ar.WARRANTY_COL_OPENED],
                               ar.WARRANTY_CLAIMS_TITLE)
        lay.addWidget(self.table)
        self.reload()

    def reload(self) -> None:
        self._claims = warranty_service.list_claims(self.session, self.user, self.filter.currentData())
        rows = [[c.sale_item.sale.invoice_no, c.sale_item.product.name, c.issue, STATUS_AR[c.status],
                 ar.YES if c.in_warranty else ar.NO, clock.fmt_local(c.opened_at)] for c in self._claims]
        self.table.set_rows(rows, keys=[c.id for c in self._claims])

    def _change_status(self) -> None:
        claim_id = self.table.selected_key()
        if claim_id is None:
            return
        labels = [STATUS_AR[k] for k in ("in_repair", "resolved", "rejected")]
        choice, ok = QInputDialog.getItem(self, ar.WARRANTY_SET_STATUS, ar.WARRANTY_COL_STATUS, labels, 0, False)
        if not ok:
            return
        status = [k for k in ("in_repair", "resolved", "rejected") if STATUS_AR[k] == choice][0]
        resolution = ""
        if status != "in_repair":
            resolution, ok = QInputDialog.getMultiLineText(self, ar.WARRANTY_SET_STATUS, ar.WARRANTY_RESOLUTION_PROMPT)
            if not ok:
                return
        try:
            warranty_service.update_claim(self.session, self.user, claim_id, status, resolution)
            self.session.commit()
        except Exception as exc:  # noqa: BLE001 - shown as an Arabic message
            self.session.rollback()
            show_error(self, exc)
            return
        show_toast(self, STATUS_AR[status])
        self.reload()
