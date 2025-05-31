# Pre-commit script for ripper project (PowerShell)
# This script calls the main Python pre-commit script

$ErrorActionPreference = "Stop"

try {
    # Run the Python pre-commit script
    python scripts/pre-commit.py
    exit $LASTEXITCODE
}
catch {
    Write-Host "Failed to run pre-commit script: $_" -ForegroundColor Red
    exit 1
}
