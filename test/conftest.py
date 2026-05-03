"""
Pytest configuration file.

This file contains fixtures and configuration for pytest.
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_DATA_HOME", os.path.join(tempfile.gettempdir(), "ripper-test-data"))
Path(os.environ["XDG_DATA_HOME"]).mkdir(parents=True, exist_ok=True)

# Fixed timestamp for testing
TEST_TIMESTAMP = datetime.now(timezone.utc)


@pytest.fixture
def test_timestamp() -> datetime:
    """Return a fixed timestamp for testing."""
    return TEST_TIMESTAMP
