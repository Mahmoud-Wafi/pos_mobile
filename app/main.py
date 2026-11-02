"""Main entry point for the shop management application."""
import sys


def main() -> None:
    """Start the application."""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from app.ui.theme import setup_theme
        from app.ui.main_window import MainWindow
        from app.core.database import init_db, session_scope
        from app.core.seed import seed_database

        app = QApplication(sys.argv)
        app.setLayoutDirection(Qt.RightToLeft)

        # Apply global modern theme & Cairo font
        setup_theme(app)

        # Ensure DB exists and is seeded
        init_db()
        with session_scope() as session:
            seed_database(session)

        window = MainWindow()
        window.show()
        sys.exit(app.exec())

    except ImportError:
        # Headless fallback
        from app.core.database import init_db, session_scope
        from app.core.seed import seed_database

        init_db()
        with session_scope() as session:
            seed_database(session)


if __name__ == "__main__":
    main()
