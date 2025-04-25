import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def build_service(credentials, service_name, version):
    try:
        return build(service_name, version, credentials=credentials)
    except HttpError as err:
        logging.error(f'An error occurred: {err}')
        return None

def fetch_transactions(credentials, spreadsheet_id, range_name):
    service = build_service(credentials, 'sheets', 'v4')
    if not service:
        return []

    try:
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])

        if not values:
            logging.info('No data found in the spreadsheet.')
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
        logging.error(f'An error occurred: {err}')
        return []

def list_google_sheets(credentials):
    service = build_service(credentials, 'drive', 'v3')
    if not service:
        return []

    try:
        results = service.files().list(q="mimeType='application/vnd.google-apps.spreadsheet'",
                                       fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            logging.info('No Google Sheets found.')
            return []

        sheets = [{'id': item['id'], 'name': item['name']} for item in items]
        return sheets

    except HttpError as err:
        logging.error(f'An error occurred: {err}')
        return []

def search_google_sheets(credentials, query):
    service = build_service(credentials, 'drive', 'v3')
    if not service:
        return []

    try:
        results = service.files().list(q=f"mimeType='application/vnd.google-apps.spreadsheet' and name contains '{query}'",
                                       fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            logging.info('No Google Sheets found matching the query.')
            return []

        sheets = [{'id': item['id'], 'name': item['name']} for item in items]
        return sheets

    except HttpError as err:
        logging.error(f'An error occurred: {err}')
        return []

def filter_google_sheets(credentials, criteria):
    service = build_service(credentials, 'drive', 'v3')
    if not service:
        return []

    try:
        query = "mimeType='application/vnd.google-apps.spreadsheet'"
        for key, value in criteria.items():
            query += f" and {key}='{value}'"
        results = service.files().list(q=query, fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            logging.info('No Google Sheets found matching the criteria.')
            return []

        sheets = [{'id': item['id'], 'name': item['name']} for item in items]
        return sheets

    except HttpError as err:
        logging.error(f'An error occurred: {err}')
        return []
