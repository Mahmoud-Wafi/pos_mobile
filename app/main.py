"""Main entry point for the shop management application.

Usage:
    python -m app.main
"""
import sys


def main() -> None:
    """Start the application."""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from app.ui.main_window import MainWindow
        from app.core.database import init_db
        from app.core.seed import seed_database
        from app.core.database import session_scope

        app = QApplication(sys.argv)
        app.setLayoutDirection(Qt.RightToLeft)

        # Ensure DB exists and is seeded
        init_db()
        with session_scope() as session:
            seed_database(session)

        window = MainWindow()
        window.show()
        sys.exit(app.exec())

    except ImportError:
        # Headless / no PySide6 — just init DB and seed
        from app.core.database import init_db
        from app.core.seed import seed_database
        from app.core.database import session_scope

        init_db()
        with session_scope() as session:
            seed_database(session)


if __name__ == "__main__":
    main()
