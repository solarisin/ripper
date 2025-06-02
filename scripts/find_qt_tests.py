#!/usr/bin/env python3
"""
Script to find test files that import from PySide6 modules.
Used in CI to automatically generate the list of test files to ignore.
"""

import os
import re
from pathlib import Path

from beartype.typing import List


def find_qt_test_files(test_dir: Path) -> List[str]:
    """
    Find all test files that import from PySide6 GUI modules.

    Only excludes tests that import GUI-related modules, as QtCore works fine in headless CI.

    Args:
        test_dir: Path to the test directory

    Returns:
        List of relative paths to test files that import PySide6 GUI modules
    """
    qt_test_files = []

    # GUI-related PySide6 modules that require a display
    gui_modules = [
        "QtWidgets",
        "QtGui",
        "QtOpenGL",
        "QtOpenGLWidgets",
        "QtQuick",
        "QtQuickWidgets",
        "QtQml",
        "QtCharts",
        "QtDataVisualization",
        "QtWebEngine",
        "QtWebEngineWidgets",
        "QtPrintSupport",
    ]

    # Create pattern to match GUI module imports
    gui_modules_pattern = "|".join(gui_modules)
    pyside6_gui_pattern = re.compile(
        rf"^\s*from\s+PySide6\s*\.\s*({gui_modules_pattern})\s+import|"
        rf"^\s*import\s+PySide6\s*\.\s*({gui_modules_pattern})",
        re.MULTILINE,
    )
    # Walk through all Python test files
    for test_file in test_dir.rglob("test_*.py"):
        try:
            with open(test_file, "r", encoding="utf-8") as f:
                content = f.read()

            # Check if file imports PySide6 GUI modules
            if pyside6_gui_pattern.search(content):
                # Get path relative to project root
                relative_path = test_file.relative_to(test_dir.parent)
                qt_test_files.append(str(relative_path).replace("\\", "/"))

        except (OSError, UnicodeDecodeError) as e:
            print(f"Warning: Could not read {test_file}: {e}")
            continue

    return sorted(qt_test_files)


def generate_pytest_ignore_args(qt_test_files: List[str]) -> str:
    """
    Generate pytest ignore arguments for the given test files.

    Args:
        qt_test_files: List of test file paths to ignore

    Returns:
        String containing pytest ignore arguments
    """
    if not qt_test_files:
        return ""

    ignore_args = []
    for test_file in qt_test_files:
        ignore_args.append(f"--ignore={test_file}")

    return " \\\n          ".join(ignore_args)


def main() -> None:
    """Main function to find Qt test files and output ignore arguments."""
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    test_dir = project_root / "test"

    if not test_dir.exists():
        print("Error: test directory not found")
        return

    # Find Qt test files
    qt_test_files = find_qt_test_files(test_dir)

    if not qt_test_files:
        print("No Qt test files found")
        return

    # Generate ignore arguments
    ignore_args = generate_pytest_ignore_args(qt_test_files)

    # Output the ignore arguments (will be captured by CI)
    print(ignore_args)


if __name__ == "__main__":
    main()
