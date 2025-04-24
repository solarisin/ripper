@echo off

REM Check for Python3 installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python3 could not be found. Please install Python3.
    exit /b 1
)

REM Check for pip installation
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo pip could not be found. Please install pip.
    exit /b 1
)

REM Create virtual environment
if not exist "venv" (
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate

REM Install dependencies
pip install -r requirements.txt

REM Launch the application
python src/main.py
