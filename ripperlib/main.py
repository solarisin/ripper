import importlib.metadata
import logging
import sys
from pathlib import Path

import toml
from PySide6.QtWidgets import QApplication

from rippergui.mainview import MainView
from ripperlib.auth import AuthManager

project_path = Path(__file__).parent.parent.resolve()


def get_version():
    try:
        version = importlib.metadata.version("ProjectName")
        return version
    except importlib.metadata.PackageNotFoundError:
        pass
    pyproject_toml = toml.load(str(project_path / "pyproject.toml"))
    return pyproject_toml["project"]["version"]


def main_gui():
    logging.info(f"Starting ripper v{get_version()}")
    # test_service_creation()
    app = QApplication(sys.argv)
    main_view = MainView()
    AuthManager().check_stored_credentials()
    main_view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # TODO add logging levels to configuration
    logging.basicConfig(level=logging.DEBUG)
    main_gui()
