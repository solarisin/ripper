# Testing Documentation for Ripper Project

This document provides an overview of the testing approach for the Ripper project, including information about what was tested, how API calls were mocked, and any issues encountered.

## Testing Approach

The testing approach for the Ripper project focuses on:

1. **Unit Testing**: Testing individual components in isolation
2. **Mocking External Dependencies**: Ensuring that tests don't make actual API calls
3. **GUI Testing**: Testing GUI components where appropriate

### Test Structure

The test directory structure mirrors the project structure:

```
test/
├── conftest.py                 # Pytest configuration
├── README.md                   # This documentation
├── ripperlib/                  # Tests for ripperlib modules
│   ├── test_auth.py            # Tests for auth.py
│   ├── test_database.py        # Tests for database.py
│   ├── test_main.py            # Tests for main.py
│   └── test_sheets_backend.py  # Tests for sheets_backend.py
└── rippergui/                  # Tests for rippergui modules
    └── test_table_view.py      # Tests for table_view.py
```

## Mocking Strategy

### Google API Mocking

All Google API calls are mocked to prevent actual network requests during testing:

1. **Sheets API**: Mocked using `unittest.mock.MagicMock` to simulate responses from Google Sheets API
2. **Drive API**: Mocked to simulate responses from Google Drive API
3. **OAuth2 Authentication**: Mocked to simulate the authentication flow without requiring user interaction

Example from `test_sheets_backend.py`:

```python
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
```

### Database Mocking

Database operations are mocked to prevent actual database creation and modification:

1. **SQLite Connections**: Mocked to simulate database connections
2. **Cursors**: Mocked to simulate query execution
3. **Query Results**: Mocked to simulate query results

Example from `test_database.py`:

```python
@patch('ripperlib.database.create_connection')
def test_retrieve_transactions_success(self, mock_create_connection):
    # Set up the mocks
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        (1, "2023-01-01", "Test Transaction 1", 100.0, "Test"),
        (2, "2023-01-02", "Test Transaction 2", 200.0, "Test")
    ]
    mock_conn.cursor.return_value = mock_cursor
    mock_create_connection.return_value = mock_conn

    # Call retrieve_transactions
    result = retrieve_transactions()

    # Check that the result contains the expected transactions
    expected_transactions = [
        {"date": "2023-01-01", "description": "Test Transaction 1", "amount": 100.0, "category": "Test"},
        {"date": "2023-01-02", "description": "Test Transaction 2", "amount": 200.0, "category": "Test"}
    ]
    self.assertEqual(result, expected_transactions)
```

### GUI Testing

GUI components are tested using `pytest-qt`:

1. **Widget Creation**: Testing that widgets initialize correctly
2. **Signal Handling**: Testing that signals are emitted and handled correctly
3. **User Interaction**: Simulating user interactions like button clicks

Example from `test_table_view.py`:

```python
def test_initialization(self, qtbot):
    # Create the widget with sample data
    widget = TransactionTableViewWidget(simulate=True)
    qtbot.addWidget(widget)
    
    # Check that the model was initialized with sample data
    assert widget.source_model.rowCount() == len(sample_transactions)
    
    # Check that the table view was set up correctly
    assert widget.table_view.isSortingEnabled()
    assert widget.table_view.alternatingRowColors()
```

## Test Coverage

The following modules have been tested:

### ripperlib

1. **auth.py**: Authentication with Google API
   - AuthState enum
   - AuthInfo class
   - TokenStore class
   - AuthManager class

2. **database.py**: Database operations
   - ConnectionPool class
   - Database utility functions
   - Transaction operations
   - Data source operations
   - Thumbnail operations

3. **main.py**: Application entry point
   - Version retrieval
   - Logging configuration
   - GUI initialization

4. **sheets_backend.py**: Google Sheets operations
   - Listing sheets
   - Reading data from spreadsheets

### rippergui

1. **table_view.py**: Table view for displaying data
   - TransactionModel class
   - TransactionSortFilterProxyModel class
   - FilterDialog class
   - TransactionTableViewWidget class

## Known Issues

1. **AuthManager Tests**: Some tests for the AuthManager class are failing due to issues with signal handling and mocking the Google API build function. These tests need to be fixed to properly mock the signals and the Google API build function.

2. **Database Schema Test**: The test for the `create_table` function in database.py is failing because it expects 7 SQL execute calls but the actual code only makes 6 calls. This suggests that either the test is incorrect or the database schema has changed since the test was written.

3. **Signal Timeout in GUI Tests**: The test for clearing filters in the TransactionTableViewWidget is failing because the expected signal is not being emitted within the timeout period. This suggests that either the signal is not being emitted at all or it's being emitted after the timeout.

4. **Unknown pytest marks**: There are warnings about unknown pytest marks (`@pytest.mark.qt`). These should be registered in pytest.ini to avoid warnings.

## Running Tests

To run all tests:

```bash
python -m pytest
```

To run tests for a specific module:

```bash
python -m pytest test/ripperlib/test_sheets_backend.py
```

To run a specific test:

```bash
python -m pytest test/ripperlib/test_sheets_backend.py::TestSheetsBackend::test_list_sheets_success
```

To run tests with verbose output:

```bash
python -m pytest -v
```

## Future Improvements

1. **Fix Failing Tests**: Address the known issues mentioned above.

2. **Increase Test Coverage**: Add tests for remaining GUI components.

3. **Integration Tests**: Add integration tests to test the interaction between different components.

4. **Continuous Integration**: Set up CI/CD to run tests automatically on code changes.

5. **Code Coverage Analysis**: Add code coverage analysis to identify untested code.