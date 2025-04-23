import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SPREADSHEET_ID = 'your_spreadsheet_id'
RANGE_NAME = 'Sheet1!A:D'

def fetch_transactions(credentials):
    try:
        service = build('sheets', 'v4', credentials=credentials)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
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

        return transactions

    except HttpError as err:
        logging.error(f"HTTP error occurred: {err}")
        raise
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        raise
