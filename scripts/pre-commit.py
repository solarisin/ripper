#!/usr/bin/env python3
"""
Pre-commit script for the ripper project.

This script runs all code quality checks including:
- flake8 for code style
- mypy for type checking
- pytest for tests

Exit codes:
- 0: All checks passed
- 1: One or more checks failed
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def run_command(command: List[str], description: str) -> Tuple[bool, str]:
    """
    Run a command and return success status and output.

    Args:
        command: List of command parts to execute
        description: Human-readable description of the command

    Returns:
        Tuple of (success: bool, output: str)    """
    print(f"🔍 Running {description}...")
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=Path(__file__).parent.parent
        )

        if result.returncode == 0:
            print(f"✅ {description} passed")
            return True, result.stdout
        else:
            print(f"❌ {description} failed")
            print(f"Return code: {result.returncode}")
            if result.stdout:
                print("STDOUT:")
                print(result.stdout)
            if result.stderr:
                print("STDERR:")
                print(result.stderr)
            return False, result.stderr or result.stdout

    except FileNotFoundError as e:
        print(f"❌ {description} failed - command not found: {e}")
        return False, str(e)
    except Exception as e:
        print(f"❌ {description} failed with exception: {e}")
        return False, str(e)


def main() -> int:
    """
    Run all pre-commit checks.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("🚀 Starting pre-commit checks for ripper project")
    print("=" * 60)

    # Track overall success
    all_passed = True

    # List of checks to run
    checks = [
        (["poetry", "run", "flake8"], "Code style check (flake8)"),
        (["poetry", "run", "mypy"], "Type checking (mypy)"),
        (["poetry", "run", "pytest"], "Unit tests (pytest)"),
    ]

    # Run each check
    for command, description in checks:
        success, output = run_command(command, description)
        if not success:
            all_passed = False
        print()  # Add spacing between checks

    # Final summary
    print("=" * 60)
    if all_passed:
        print("🎉 All pre-commit checks passed!")
        return 0
    else:
        print("💥 Some pre-commit checks failed!")
        print("Please fix the issues above before committing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
