import json
import keyring
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

TOKEN_KEY='ripper-gsheets'
SCOPES=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.readonly']

def authorize(client_secret_file, user_id):
    cred = None
    token = keyring.get_password(TOKEN_KEY, user_id)
    if token:
        cred = Credentials.from_authorized_user_info(json.loads(token), SCOPES)
    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            cred = flow.run_local_server(port=0)
            keyring.set_password('ripper-gsheets', user_id, cred.to_json())
    return cred

def create_sheets_service(client_secret_file, user_id='default-user'):
    cred = authorize(client_secret_file, user_id)
    return build('sheets', 'v4', credentials=cred, cache_discovery=False)

def create_drive_service(client_secret_file, user_id='default-user'):
    cred = authorize(client_secret_file, user_id)
    return build('drive', 'v3', credentials=cred, cache_discovery=False)
