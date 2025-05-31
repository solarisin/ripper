@echo off
REM Pre-commit script for ripper project (Windows batch)
REM This script calls the main Python pre-commit script

python scripts\pre-commit.py
exit /b %ERRORLEVEL%
