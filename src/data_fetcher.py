import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from database import insert_transaction

DEFAULT_SPREADSHEET_ID = 'your_spreadsheet_id'
DEFAULT_RANGE_NAME = 'Transactions!A:D'

def fetch_transactions(credentials, spreadsheet_id=DEFAULT_SPREADSHEET_ID, range_name=DEFAULT_RANGE_NAME):
    try:
        service = build('sheets', 'v4', credentials=credentials)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])

        if not values:
            logging.info('No data found.')
            return []

        transactions = []
        for row in values[1:]:
            transaction = {
                'date': row[0],
                'description': row[1],
                'amount': float(row[2]),
                'category': row[3]
            }
            transactions.append(transaction)
            insert_transaction(transaction)

        return transactions

    except HttpError as err:
        logging.error(f"HTTP error occurred: {err}")
        raise
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        raise
