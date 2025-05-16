# Ripper Project Guidelines

This document provides guidelines and information for developing and maintaining the Ripper project.

## Project Overview

Ripper is a GUI application for extracting and analyzing data from Google Sheets. It uses PySide6 (Qt for Python) for 
the UI and Google API for authentication and data access.

### Target Use Cases
- Extract bank transaction data from a Tiller Google Sheet that is updated regularly with new transaction information.
- This data is synchronized to a local database upon user request.
- The local data can then be visualized using custom tables, graphs, charts and other methods.

## Build/Configuration Instructions

### Prerequisites

- Python 3.11 or newer (up to 3.13)
- Poetry (dependency management)

### Setting Up the Development Environment

1. Clone the repository:
   ```bash
   git clone https://github.com/solarisin/ripper.git
   cd ripper
   ```

2. Install dependencies using Poetry:
   ```bash
   poetry install
   ```

3. Activate the Poetry virtual environment:
   ```bash
   poetry shell
   ```

### Google API Configuration

To use the application, you need to set up Google OAuth credentials:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Sheets API and Google Drive API
4. Create OAuth 2.0 credentials (Desktop application type)
5. Download the credentials JSON file
6. When running the application, use the "OAuth" menu to register your credentials

## Testing Information

### Test Structure

- Tests are located in the `test` directory
- The directory structure mirrors the project structure (e.g., `test/ripperlib` for tests of `ripperlib` modules)
- `conftest.py` in the test directory configures pytest for the project

### Running Tests

Run all tests:
```bash
python -m pytest
```

Run tests with verbose output:
```bash
python -m pytest -v
```

Run tests for a specific module:
```bash
python -m pytest test/ripperlib/test_sheets_backend.py
```

Run a specific test:
```bash
python -m pytest test/ripperlib/test_sheets_backend.py::TestSheetsBackend::test_list_sheets_success
```

### Writing Tests

1. Create test files with the naming convention `test_*.py`
2. Use unittest or pytest style tests (the project uses both)
3. Use mocking for external dependencies (especially Google API calls)

Example test:
```python
import unittest
from unittest.mock import MagicMock

from ripperlib.sheets_backend import list_sheets

class TestSheetsBackend(unittest.TestCase):
    def test_list_sheets_success(self):
        # Create a mock service
        mock_service = MagicMock()

        # Set up the mock to return a response with files
        mock_files_list = mock_service.files.return_value.list
        mock_files_list.return_value.execute.return_value = {
            "files": [
                {"id": "sheet1", "name": "Test Sheet 1"},
                {"id": "sheet2", "name": "Test Sheet 2"},
            ],
            "nextPageToken": None
        }

        # Call the function with our mock
        result = list_sheets(mock_service)

        # Verify the result
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "sheet1")
        self.assertEqual(result[0]["name"], "Test Sheet 1")
```

### Testing GUI Components

For testing GUI components, use the `pytest-qt` plugin:

```python
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton
from rippergui.mainview import MainView

def test_main_view_initialization(qtbot):
    # Create the widget
    widget = MainView()
    qtbot.addWidget(widget)

    # Check that the window title is correct
    assert widget.windowTitle() == "ripper"

    # Test a button click
    qtbot.mouseClick(widget.findChild(QPushButton, "some_button"), Qt.LeftButton)

    # Check the result of the button click
    assert some_condition_is_true
```

## Additional Development Information

### Project Structure

- `ripperlib/`: Core functionality
  - `auth.py`: Authentication with Google API
  - `sheets_backend.py`: Interaction with Google Sheets
  - `main.py`: Application entry point
- `rippergui/`: GUI components
  - `mainview.py`: Main application window
  - `sheets_selection_view.py`: Dialog for selecting Google Sheets
  - `table_view.py`: Table view for displaying spreadsheet data
- `test/`: Test files

### Code Style

The project uses:
- Black for code formatting (line length: 120)
- Flake8 for linting

Format code with Black:
```bash
poetry run black .
```

Check code with Flake8:
```bash
poetry run flake8
```

### Authentication Flow

1. The user configures OAuth client credentials (client ID and secret)
2. The application stores these credentials securely using the system keyring
3. When the user authenticates, the application starts an OAuth flow
4. After successful authentication, the token is stored in the keyring
5. The application uses the token to access Google Sheets and Drive APIs

### Adding New Features

When adding new features:
1. Add appropriate tests
2. Follow the existing code structure
3. Update documentation as needed
4. Ensure the UI is responsive and user-friendly
