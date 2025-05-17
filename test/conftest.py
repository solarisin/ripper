"""
Pytest configuration file.

This file contains fixtures and configuration for pytest.
"""

import logging
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)
