import importlib.metadata
import logging
import sys
import toml
from pathlib import Path
from typing import Optional
from PySide6.QtWidgets import QApplication
from rippergui.mainview import MainView
from ripperlib.auth import AuthManager

# Get the project root path
project_path = Path(__file__).parent.parent.resolve()

# Configure logger
log = logging.getLogger("ripper:main")


def get_version() -> str:
    """
    Get the current version of the application.

    First tries to get the version from the installed package metadata.
    If that fails, reads it from the pyproject.toml file.

    Returns:
        The version string
    """
    try:
        # Try to get version from package metadata (when installed)
        version = importlib.metadata.version("ripper")
        return version
    except importlib.metadata.PackageNotFoundError:
        # Fall back to reading from pyproject.toml
        log.debug("Package not installed, reading version from pyproject.toml")
        pyproject_toml = toml.load(str(project_path / "pyproject.toml"))
        return pyproject_toml["project"]["version"]


def configure_logging(level: Optional[int] = None) -> None:
    """
    Configure the application's logging.

    Args:
        level: The logging level to use. If None, uses DEBUG.
    """
    if level is None:
        level = logging.DEBUG

    # Configure root logger
    logging.basicConfig(
        level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    log.debug(f"Logging configured with level: {logging.getLevelName(level)}")


def main_gui() -> None:
    """
    Start the GUI application.

    This is the main entry point for the GUI version of the application.
    """
    log.info(f"Starting ripper v{get_version()}")

    app = QApplication(sys.argv)
    main_view = MainView()
    AuthManager().check_stored_credentials()
    main_view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    configure_logging()
    main_gui()
