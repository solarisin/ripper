import importlib.metadata
import logging
import sys
from pathlib import Path

import click
import toml
from PySide6.QtWidgets import QApplication
from beartype.typing import Optional
from click import pass_context

import ripper.ripperlib.database
from ripper.rippergui.mainview import MainView
from ripper.ripperlib.auth import AuthManager
from ripper.ripperlib.database import Db

# Get the project root path
project_path = Path(__file__).parent.parent.resolve()


def get_version() -> str:
    """
    Get the current version of the application.

    First tries to get the version from the installed package metadata.
    If that fails, reads it from the pyproject.toml file.

    Returns:
        The version string
    """
    log = logging.getLogger("ripper:version")

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
    logging.debug(f"Logging configured with level: {logging.getLevelName(level)}")


def log_context(ctx: click.Context) -> None:
    log = logging.getLogger("ripper:cli")
    if ctx.obj is not None and "DEBUG_CLI" in ctx.obj and ctx.obj["DEBUG_CLI"]:
        if ctx.parent is not None:
            log_context(ctx.parent)
        log.debug(f"======= {ctx.command.name} =======")
        log.debug(f"ctx.params: {ctx.params}")
        log.debug(f"ctx.args: {ctx.args}")
        log.debug(f"ctx.invoked_subcommand: {ctx.invoked_subcommand}")
        log.debug(f"ctx.parent: {ctx.parent}")
        log.debug(f"ctx.command_path: {ctx.command_path}")
        log.debug(f"ctx.obj: {ctx.obj}")


@click.group(invoke_without_command=True)
@pass_context
@click.option(
    "--clear-credential-cache",
    "-c",
    is_flag=True,
    help="Clear the credential cache before starting, forces re-authentication",
)
@click.option(
    "--debug-cli",
    is_flag=True,
    help="Print verbose debug messages about CLI execution",
)
def cli(ctx: click.Context, clear_credential_cache: bool = False, debug_cli: bool = False) -> int:
    """Ripper application command line interface."""
    # Always executed first, even for subcommands
    configure_logging()

    ctx.ensure_object(dict)
    ctx.obj["VERSION"] = get_version()
    ctx.obj["CLI_LOGGER"] = logging.getLogger("ripper:cli")
    ctx.obj["DEBUG_CLI"] = debug_cli

    # Only execute if this is the main command (no subcommand)
    if ctx.invoked_subcommand is None:

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
    return 0


@cli.group()
@click.pass_context
@click.option(
    "--file-path",
    "-f",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    help="Path to the database file to operate on",
)
def db(ctx: click.Context, file_path: Path | None) -> None:
    """Database management commands."""
    if file_path is None:
        ctx.obj["DB_PATH"] = ripper.ripperlib.database.default_db_path()
    else:
        ctx.obj["DB_PATH"] = file_path
    ctx.obj["CLI_LOGGER"] = logging.getLogger("ripper:cli:db")


@db.command()
@click.pass_context
def create(ctx: click.Context) -> None:
    """Create database tables."""
    log = ctx.obj["CLI_LOGGER"]
    log_context(ctx)

    db_path: Path = ctx.obj["DB_PATH"]
    log.debug(f"db absolute path: {db_path.absolute()}")

    if not db_path.exists():
        try:
            log.debug(f"Creating database at {db_path}")
            Db().open()
        finally:
            Db().close()
    else:
        log.debug(f"Database at {db_path} already exists, skipping create")


@db.command()
@click.pass_context
def clean(ctx: click.Context) -> None:
    """Create database tables."""
    log_context(ctx)
    log = ctx.obj["CLI_LOGGER"]

    db_path: Path = ctx.obj["DB_PATH"]
    if db_path.exists():
        log.debug(f"Cleaning database at {db_path}")
        db_path.unlink()
    else:
        log.debug(f"Database at {db_path} does not exist, skipping clean")


if __name__ == "__main__":
    cli(obj={})
