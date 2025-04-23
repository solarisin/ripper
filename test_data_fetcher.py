import pytest
from unittest.mock import patch, MagicMock
from googleapiclient.errors import HttpError
from data_fetcher import fetch_transactions

@patch('data_fetcher.build')
def test_fetch_transactions_success(mock_build):
    mock_service = MagicMock()
    mock_sheet = MagicMock()
    mock_service.spreadsheets.return_value = mock_sheet
    mock_build.return_value = mock_service

    mock_sheet.values().get.return_value.execute.return_value = {
        'values': [
            ['Date', 'Description', 'Amount', 'Category'],
            ['2021-01-01', 'Test Transaction', '100.0', 'Test Category']
        ]
    }

    credentials = MagicMock()
    transactions = fetch_transactions(credentials)

    assert len(transactions) == 1
    assert transactions[0]['date'] == '2021-01-01'
    assert transactions[0]['description'] == 'Test Transaction'
    assert transactions[0]['amount'] == 100.0
    assert transactions[0]['category'] == 'Test Category'

@patch('data_fetcher.build')
def test_fetch_transactions_no_data(mock_build):
    mock_service = MagicMock()
    mock_sheet = MagicMock()
    mock_service.spreadsheets.return_value = mock_sheet
    mock_build.return_value = mock_service

    mock_sheet.values().get.return_value.execute.return_value = {
        'values': []
    }

    credentials = MagicMock()
    transactions = fetch_transactions(credentials)

    assert len(transactions) == 0

@patch('data_fetcher.build')
def test_fetch_transactions_http_error(mock_build):
    mock_service = MagicMock()
    mock_sheet = MagicMock()
    mock_service.spreadsheets.return_value = mock_sheet
    mock_build.return_value = mock_service

    mock_sheet.values().get.side_effect = HttpError(MagicMock(), b'Error')

    credentials = MagicMock()
    with pytest.raises(HttpError):
        fetch_transactions(credentials)

@patch('data_fetcher.build')
def test_fetch_transactions_general_error(mock_build):
    mock_service = MagicMock()
    mock_sheet = MagicMock()
    mock_service.spreadsheets.return_value = mock_sheet
    mock_build.return_value = mock_service

    mock_sheet.values().get.side_effect = Exception('General error')

    credentials = MagicMock()
    with pytest.raises(Exception):
        fetch_transactions(credentials)
