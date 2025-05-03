import sys
import logging
import toml
from PySide6.QtWidgets import QApplication
from widgets.main_window import MainWindow
from notifications import NotificationSystem
import importlib.metadata
from pathlib import Path

logging.basicConfig(level=logging.INFO)

def get_version():
    try:
        version = importlib.metadata.version('ProjectName')
        return version
    except importlib.metadata.PackageNotFoundError:
        pass
    project_path = Path(__file__).parent.parent.resolve()
    pyproject_toml = toml.load(str(project_path / 'pyproject.toml'))
    return pyproject_toml['tool']['poetry']['version']


def main_gui():
    logging.info(f"Starting ripper v{get_version()}")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.notification_system = NotificationSystem()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main_gui()