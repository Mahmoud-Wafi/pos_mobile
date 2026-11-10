"""Main entry point for the shop management application."""
import sys


def _show_error_dialog(details: str) -> None:
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox()
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle("خطأ غير متوقع")
    box.setText("حدث خطأ غير متوقع. تم تسجيل التفاصيل في ملف السجل.\nيمكنك المتابعة، وإن تكرر الخطأ يرجى إبلاغ الدعم الفني.")
    box.setDetailedText(details)
    box.exec()


def main() -> None:
    """Start the application."""
    from app.core import startup

    startup.setup_logging()
    startup.install_excepthook()

    from app.core.database import session_scope
    from app.core.seed import seed_database

    # Schema is managed by Alembic in production (D-002); tests use create_all.
    startup.run_migrations()
    with session_scope() as session:
        seed_database(session)

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from app.ui.theme import setup_theme

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    setup_theme(app)
    startup.install_excepthook(_show_error_dialog)

    from app.ui.session import run_with_login

    sys.exit(run_with_login(app))


if __name__ == "__main__":
    main()
