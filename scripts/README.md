# Pre-commit Scripts

This directory contains pre-commit scripts for the ripper project that run all code quality checks before committing changes.

# Pre-commit Scripts

This directory contains pre-commit scripts for the ripper project that run all code quality checks before committing changes.

## Available Scripts

### Python Script (Main Implementation)
```bash
python scripts/pre-commit.py
```
- Cross-platform implementation with detailed error reporting
- Returns proper exit codes
- Contains the main logic for all checks

### PowerShell Wrapper (Windows)
```powershell
powershell -ExecutionPolicy Bypass -File scripts/pre-commit.ps1
```
- Simple wrapper that calls the Python script
- Handles PowerShell-specific error handling

### Bash Wrapper (Unix/Linux/macOS)
```bash
./scripts/pre-commit.sh
```
- Simple wrapper that calls the Python script
- Requires executable permissions: `chmod +x scripts/pre-commit.sh`

### Batch Wrapper (Windows)
```cmd
scripts\pre-commit.bat
```
- Simple wrapper that calls the Python script
- For Windows Command Prompt

## What the Scripts Do

All scripts run the main Python implementation which performs these checks in order:

1. **flake8** - Code style checking
2. **mypy** - Type hint validation  
3. **pytest** - Run all unit tests

If any check fails, the script stops and returns a non-zero exit code.

## Design

The Python script (`pre-commit.py`) contains the main implementation, while the other scripts are simple wrappers that:
- Call the Python script
- Pass through the exit code
- Provide platform-specific conveniences

This design ensures:
- ✅ **Single source of truth** - All logic is in one place
- ✅ **Easy maintenance** - Updates only needed in Python script
- ✅ **Consistent behavior** - All platforms run identical checks
- ✅ **Platform flexibility** - Use the wrapper that fits your workflow

## Usage in Git Hooks

To automatically run these checks before each commit, you can set up a git pre-commit hook:

### Option 1: Python Script Hook
Create `.git/hooks/pre-commit` (no extension):
```bash
#!/bin/sh
python scripts/pre-commit.py
```

### Option 2: PowerShell Script Hook (Windows)
Create `.git/hooks/pre-commit` (no extension):
```bash
#!/bin/sh
powershell -ExecutionPolicy Bypass -File scripts/pre-commit.ps1
```

Then make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

## Manual Usage

You can run any of these scripts manually before committing to ensure your changes pass all quality checks:

```bash
# Run before committing
python scripts/pre-commit.py

# If all checks pass, proceed with commit
git commit -m "Your commit message"
```

## Requirements

- Poetry must be installed and configured
- All project dependencies must be installed via `poetry install`
- The scripts must be run from the project root directory

## Exit Codes

- **0**: All checks passed successfully
- **1**: One or more checks failed

This follows standard Unix conventions for exit codes.
