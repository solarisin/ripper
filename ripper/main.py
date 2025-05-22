import importlib.metadata
import logging
import sys
from pathlib import Path

import click
import toml
from beartype.typing import Optional
from PySide6.QtWidgets import QApplication

from ripper.rippergui.mainview import MainView
from ripper.ripperlib.auth import AuthManager
from ripper.ripperlib.database import Db

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
        return str(version)
    except importlib.metadata.PackageNotFoundError:
        # Fall back to reading from pyproject.toml
        log.debug("Package not installed, reading version from pyproject.toml")
        pyproject_toml = toml.load(str(project_path / "pyproject.toml"))
        return str(pyproject_toml["project"]["version"])


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

    # Initialize the database
    Db().open()

    # Clear the credential cache if requested
    if clear_credential_cache:
        AuthManager().clear_stored_credentials()

    # Initialize the main window
    app = QApplication(sys.argv)
    main_window = MainView()
    AuthManager().check_stored_credentials()
    main_window.show()

    # Start the event loop
    try:
        return app.exec()
    finally:
        Db().close()


if __name__ == "__main__":
    main()
