#!/bin/bash
# Pre-commit script for ripper project (Bash)
# This script calls the main Python pre-commit script

python scripts/pre-commit.py
exit $?
