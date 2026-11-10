"""Session controller: login -> main window -> logout / idle lock -> login."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication

from app.core.database import get_session
from app.models.user import Setting
from app.services import auth_service
from app.ui.login_dialog import ForcePasswordDialog, LoginDialog, uses_default_password


def _idle_minutes() -> int:
    session = get_session()
    try:
        row = session.query(Setting).filter_by(key="idle_lock_minutes").first()
        return max(0, int(row.value)) if row and row.value else 10
    except (ValueError, TypeError):
        return 10
    finally:
        session.close()


class _ActivityFilter(QObject):
    """Restarts the idle timer on any user input."""

    _EVENTS = {QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.KeyPress, QEvent.Wheel}

    def __init__(self, timer: QTimer):
        super().__init__()
        self._timer = timer

    def eventFilter(self, obj, event):
        if event.type() in self._EVENTS and self._timer.isActive():
            self._timer.start()
        return False


class SessionController:
    def __init__(self, app: QApplication):
        self.app = app
        self.window = None
        self.last_username = ""
        self.idle_timer = QTimer()
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(lambda: self.lock(idle=True))
        self.activity = _ActivityFilter(self.idle_timer)
        app.installEventFilter(self.activity)
        app.setQuitOnLastWindowClosed(False)

    # -- flow -----------------------------------------------------------
    def start(self, locked: bool = False) -> int:
        dlg = LoginDialog(locked=locked, username=self.last_username if locked else "")
        if dlg.exec() != LoginDialog.Accepted or dlg.user_id is None:
            self.app.quit()
            return 0
        self._open_window(dlg.user_id)
        return 0

    def _open_window(self, user_id: int) -> None:
        from app.models.user import User
        from app.ui.main_window import MainWindow

        session = get_session()
        try:
            user = session.get(User, user_id)
            self.last_username = user.username
            force = uses_default_password(user)
        finally:
            session.close()

        if force:
            dlg = ForcePasswordDialog(user_id)
            dlg.exec()

        self.window = MainWindow(user_id=user_id)
        self.window.logout_requested.connect(self.logout)
        self.window.lock_requested.connect(lambda: self.lock(idle=False))
        self.window.closed_by_user.connect(self.app.quit)
        self.window.show()

        minutes = _idle_minutes()
        if minutes > 0:
            self.idle_timer.setInterval(minutes * 60_000)
            self.idle_timer.start()

    def _close_window(self) -> None:
        self.idle_timer.stop()
        if self.window is not None:
            self.window.close_for_logout()
            self.window.deleteLater()
            self.window = None

    def logout(self) -> None:
        self._audit("logout")
        self._close_window()
        self.last_username = ""
        self.start(locked=False)

    def lock(self, idle: bool) -> None:
        if self.window is None:
            return
        self._audit("idle_lock" if idle else "manual_lock")
        self._close_window()
        self.start(locked=True)

    def _audit(self, action: str) -> None:
        if self.window is None:
            return
        session = get_session()
        try:
            from app.models.user import User
            user = session.get(User, self.window.user_id)
            if user is not None:
                if action == "logout":
                    auth_service.logout(session, user)
                else:
                    from app.core.audit import log_action
                    log_action(session, action, user_id=user.id, table_name="users", record_id=user.id)
                    session.commit()
        finally:
            session.close()


def run_with_login(app: QApplication) -> int:
    controller = SessionController(app)
    controller.start()
    if controller.window is None:   # login cancelled before the event loop started
        return 0
    return app.exec()
