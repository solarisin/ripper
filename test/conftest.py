"""
Pytest configuration file.

This file contains fixtures and configuration for pytest.
"""

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Create a unique temp directory per session so parallel runs don't share state.
_XDG_DATA_HOME = tempfile.mkdtemp(prefix="ripper-test-")
os.environ["XDG_DATA_HOME"] = _XDG_DATA_HOME

# Fixed timestamp for testing
TEST_TIMESTAMP = datetime.now(timezone.utc)


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_data_dir() -> Generator[None, None, None]:
    """Remove the per-session test data directory after the test run."""
    yield
    shutil.rmtree(_XDG_DATA_HOME, ignore_errors=True)


@pytest.fixture(autouse=True)
def _isolate_global_db(tmp_path: Path) -> Generator[None, None, None]:
    """Point the application-wide `Db` singleton at a fresh temp database for every test.

    The `Db` proxy constructs the real RipperDb (at the user data dir) on first use; on
    Windows the XDG override above does not apply, so without this fixture a test that
    touches `Db` would operate on the real `ripper.db`. Injecting a per-test RipperDb keeps
    every test fully isolated from the real database.
    """
    import ripper.ripperlib.database as database

    test_db = database.RipperDb(str(tmp_path / "ripper.db"))
    previous = database.Db._instance
    database.Db._instance = test_db
    try:
        yield
    finally:
        test_db.close()
        database.Db._instance = previous


@pytest.fixture
def test_timestamp() -> datetime:
    """Return a fixed timestamp for testing."""
    return TEST_TIMESTAMP
