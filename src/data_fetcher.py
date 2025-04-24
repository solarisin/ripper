import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from database import insert_transaction

DEFAULT_SPREADSHEET_ID = 'your_spreadsheet_id'
DEFAULT_RANGE_NAME = 'Transactions!A:D'
