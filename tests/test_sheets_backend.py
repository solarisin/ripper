import pytest
from unittest.mock import patch, MagicMock
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sheets_backend import list_google_sheets, search_google_sheets, filter_google_sheets, fetch_transactions

def test_list_google_sheets():
    with patch('sheets_backend.build') as mock_build:
        mock_service = MagicMock()
        mock_sheets = mock_service.spreadsheets.return_value
        mock_sheets.get.return_value.execute.return_value = {
            'sheets': [{'properties': {'title': 'Sheet1'}}, {'properties': {'title': 'Sheet2'}}]
        }
        mock_build.return_value = mock_service

        credentials = MagicMock()
        sheets = list_google_sheets(credentials)
        assert len(sheets) == 2
        assert sheets[0]['name'] == 'Sheet1'
        assert sheets[1]['name'] == 'Sheet2'

def test_search_google_sheets():
    with patch('sheets_backend.build') as mock_build:
        mock_service = MagicMock()
        mock_drive = mock_service.files.return_value
        mock_drive.list.return_value.execute.return_value = {
            'files': [{'id': 'sheet1', 'name': 'Test Sheet 1'}, {'id': 'sheet2', 'name': 'Test Sheet 2'}]
        }
        mock_build.return_value = mock_service

        credentials = MagicMock()
        sheets = search_google_sheets(credentials, 'Test')
        assert len(sheets) == 2
        assert sheets[0]['name'] == 'Test Sheet 1'
        assert sheets[1]['name'] == 'Test Sheet 2'

def test_filter_google_sheets():
    with patch('sheets_backend.build') as mock_build:
        mock_service = MagicMock()
        mock_drive = mock_service.files.return_value
        mock_drive.list.return_value.execute.return_value = {
            'files': [{'id': 'sheet1', 'name': 'Test Sheet 1', 'owners': [{'emailAddress': 'user1@example.com'}]},
                      {'id': 'sheet2', 'name': 'Test Sheet 2', 'owners': [{'emailAddress': 'user2@example.com'}]}]
        }
        mock_build.return_value = mock_service

        credentials = MagicMock()
        sheets = filter_google_sheets(credentials, {'owner': 'user1@example.com'})
        assert len(sheets) == 1
        assert sheets[0]['name'] == 'Test Sheet 1'

def test_fetch_transactions():
    with patch('sheets_backend.build') as mock_build:
        mock_service = MagicMock()
        mock_sheets = mock_service.spreadsheets.return_value
        mock_sheets.values.return_value.get.return_value.execute.return_value = {
            'values': [
                ['Date', 'Description', 'Amount', 'Category'],
                ['2022-01-01', 'Test Transaction 1', '100.0', 'Test'],
                ['2022-01-02', 'Test Transaction 2', '200.0', 'Test']
            ]
        }
        mock_build.return_value = mock_service

        credentials = MagicMock()
        transactions = fetch_transactions(credentials, 'spreadsheet_id', 'range_name')
        assert len(transactions) == 2
        assert transactions[0]['date'] == '2022-01-01'
        assert transactions[0]['description'] == 'Test Transaction 1'
        assert transactions[0]['amount'] == 100.0
        assert transactions[0]['category'] == 'Test'
        assert transactions[1]['date'] == '2022-01-02'
        assert transactions[1]['description'] == 'Test Transaction 2'
        assert transactions[1]['amount'] == 200.0
        assert transactions[1]['category'] == 'Test'
