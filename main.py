import importlib.metadata
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import click
import toml
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


def get_app_data_dir() -> str:
    """Get the application data directory."""
    app_data = os.environ.get("APPDATA")
    if not app_data:
        app_data = str(Path.home() / ".local" / "share")
    return os.path.join(app_data, "ripper")


def ensure_app_data_dir() -> None:
    """Ensure the application data directory exists."""
    app_data_dir = get_app_data_dir()
    if not os.path.exists(app_data_dir):
        os.makedirs(app_data_dir)


@click.command()
@click.option(
    "--clear-credential-cache",
    "-c",
    is_flag=True,
    help="Clear the credential cache before starting, forces re-authentication",
)
def main(clear_credential_cache: bool) -> int:
    """Main entry point for the application."""
    configure_logging()
    ensure_app_data_dir()

    if clear_credential_cache:
        AuthManager().clear_stored_credentials()

    app = QApplication(sys.argv)
    main_window = MainView()
    AuthManager().check_stored_credentials()
    main_window.show()

    return app.exec()


if __name__ == "__main__":
    main()
