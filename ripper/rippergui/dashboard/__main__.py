"""Main entry point for the financial dashboard application."""

import sys

from PySide6.QtWidgets import QApplication

from ripper.rippergui.dashboard.views.main_window import MainWindow


def main() -> int:
    """Run the financial dashboard application.

    Returns:
        int: Exit code
    """
    app = QApplication(sys.argv)

    # Set application metadata
    app.setApplicationName("Financial Dashboard")
    app.setOrganizationName("Ripper")
    app.setOrganizationDomain("ripper.app")

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run the application
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
