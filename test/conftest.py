"""
Pytest configuration file.

This file contains fixtures and configuration for pytest.
"""

from datetime import datetime, timezone

import pytest

# Fixed timestamp for testing
TEST_TIMESTAMP = datetime.now(timezone.utc)


@pytest.fixture
def test_timestamp() -> datetime:
    """Return a fixed timestamp for testing."""
    return TEST_TIMESTAMP
