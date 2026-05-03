"""
Pytest configuration file.

This file contains fixtures and configuration for pytest.
"""

import os
import shutil
import tempfile
from datetime import datetime, timezone
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


@pytest.fixture
def test_timestamp() -> datetime:
    """Return a fixed timestamp for testing."""
    return TEST_TIMESTAMP
