"""
Main entry point and CLI for the ripper application.

This module sets up logging, version retrieval, and provides a Click-based command line interface
for launching the GUI, managing the database, and other developer/maintenance tasks.
"""

import importlib.metadata
import sys
from pathlib import Path

import click
import toml
from click import pass_context
from loguru import logger
from PySide6.QtWidgets import QApplication

import ripper.ripperlib.database
from ripper.rippergui.mainview import MainView
from ripper.ripperlib.auth import AuthManager
from ripper.ripperlib.database import Db
from ripper.ripperlib.defs import LOG_FILE_PATH


def configure_logging(log_level: str = "DEBUG") -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=log_level.upper(),
        filter=lambda record: record["level"].no < 40,  # 40 is ERROR
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <7}</level> | "
            "<cyan>{file.path}</cyan>:<cyan>{line}</cyan> <light-magenta>{function}</light-magenta> - "
            "<level>{message}</level>"
        ),
    )
    stderr_level = "CRITICAL" if log_level.upper() == "CRITICAL" else "ERROR"
    logger.add(
        sys.stderr,
        level=stderr_level,
        format=(
            "<red>{time:YYYY-MM-DD HH:mm:ss}</red> | "
            "<level>{level: <7}</level> | "
            "<cyan>{file.path}</cyan>:<cyan>{line}</cyan> <light-magenta>{function}</light-magenta> - "
            "<level>{message}</level>"
        ),
    )
    logger.add(
        LOG_FILE_PATH,
        rotation="10 MB",
        retention="10 days",
        level=log_level.upper(),
        encoding="utf-8",
        format=("{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | " "{name}:{function}:{line} - {message}"),
    )


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
    try:
        # Try to get version from package metadata (when installed)
        version = importlib.metadata.version("ripper")
        return str(version)
    except importlib.metadata.PackageNotFoundError:
        pyproject_toml = toml.load(str(project_path / "pyproject.toml"))
        return str(pyproject_toml["project"]["version"])


def log_context(ctx: click.Context) -> None:
    """
    Recursively log the context and parameters for debugging CLI execution.

    Args:
        ctx (click.Context): The Click context object.
    """
    if ctx.obj is not None and "DEBUG_CLI" in ctx.obj and ctx.obj["DEBUG_CLI"]:
        if ctx.parent is not None:
            log_context(ctx.parent)
        logger.debug(f"======= {ctx.command.name} =======")
        logger.debug(f"ctx.params: {ctx.params}")
        logger.debug(f"ctx.args: {ctx.args}")
        logger.debug(f"ctx.invoked_subcommand: {ctx.invoked_subcommand}")
        logger.debug(f"ctx.parent: {ctx.parent}")
        logger.debug(f"ctx.command_path: {ctx.command_path}")
        logger.debug(f"ctx.obj: {ctx.obj}")


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
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], case_sensitive=False),
    default="DEBUG",
    show_default=True,
    help="Set the logging level for stdout and file logs.",
)
def cli(
    ctx: click.Context,
    log_level: str,
    clear_credential_cache: bool = False,
    debug_cli: bool = False,
) -> int:
    """
    Ripper application command line interface.

    This command launches the main GUI application or delegates to subcommands for database management.
    """
    # Always executed first, even for subcommands
    configure_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["VERSION"] = get_version()
    ctx.obj["DEBUG_CLI"] = debug_cli

    # Only execute if this is the main command (no subcommand)
    if ctx.invoked_subcommand is None:
        # Initialize the database
        Db.open()

        # Clear the credential cache if requested
        if clear_credential_cache:
            AuthManager().clear_stored_credentials()

        # Initialize the main window
        app = QApplication(sys.argv)

        # Set application properties
        app.setApplicationName("ripper")
        app.setOrganizationName("ripper")
        app.setApplicationVersion(ctx.obj["VERSION"])
        app.setStyle("Fusion")

        main_window = MainView()
        AuthManager().check_stored_credentials()
        main_window.show()

        # Start the event loop
        try:
            return app.exec()
        finally:
            Db.close()
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
    """
    Database management commands group.

    Args:
        ctx (click.Context): The Click context object.
        file_path (Path | None): Optional path to the database file.
    """
    if file_path is None:
        ctx.obj["DB_PATH"] = ripper.ripperlib.database.default_db_path()
    else:
        ctx.obj["DB_PATH"] = file_path


@db.command()
@click.pass_context
def create(ctx: click.Context) -> None:
    """
    Create database tables if the database does not already exist.

    Args:
        ctx (click.Context): The Click context object.
    """
    log_context(ctx)
    db_path: Path = ctx.obj["DB_PATH"]
    logger.debug(f"db absolute path: {db_path.absolute()}")

    if not db_path.exists():
        try:
            logger.debug(f"Creating database at {db_path}")
            Db.open()
        finally:
            Db.close()
    else:
        logger.debug(f"Database at {db_path} already exists, skipping create")


@db.command()
@click.pass_context
def clean(ctx: click.Context) -> None:
    """
    Remove the database file if it exists.

    Args:
        ctx (click.Context): The Click context object.
    """
    Db.close()
    log_context(ctx)
    db_path: Path = ctx.obj["DB_PATH"]
    if db_path.exists():
        logger.debug(f"Cleaning database at {db_path}")
        db_path.unlink()
    else:
        logger.debug(f"Database at {db_path} does not exist, skipping clean")


if __name__ == "__main__":
    cli(obj={})
