#!/bin/bash

# Check for dependencies
if ! command -v python3 &> /dev/null
then
    echo "Python3 could not be found. Please install Python3."
    exit
fi

if ! command -v pip &> /dev/null
then
    echo "pip could not be found. Please install pip."
    exit
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Launch the application
python src/main.py
