import json
import keyring
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

TOKEN_KEY = 'ripper-gsheets'
OAUTH_CLIENT_KEY = 'ripper-oauth-client'
OAUTH_CLIENT_USER = 'default-user'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.readonly']

def get_client_credentials():
    """Get client credentials from keyring"""
    credentials_json = keyring.get_password(OAUTH_CLIENT_KEY, OAUTH_CLIENT_USER)
    if not credentials_json:
        return None, None

    credentials = json.loads(credentials_json)
    return credentials.get('client_id'), credentials.get('client_secret')

def create_client_config():
    """Create a client config dictionary from keyring credentials"""
    client_id, client_secret = get_client_credentials()
    if not client_id or not client_secret:
        return None

    # Create the client config dictionary
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }

    return client_config

def authorize(user_id):
    cred = None
    token = keyring.get_password(TOKEN_KEY, user_id)
    if token:
        cred = Credentials.from_authorized_user_info(json.loads(token), SCOPES)
    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        else:
            client_config = create_client_config()
            if not client_config:
                return None

            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            cred = flow.run_local_server(port=0)
            keyring.set_password(TOKEN_KEY, user_id, cred.to_json())
    return cred

def create_sheets_service(user_id='default-user'):
    cred = authorize(user_id)
    if not cred:
        return None
    return build('sheets', 'v4', credentials=cred, cache_discovery=False)

def create_drive_service(user_id='default-user'):
    cred = authorize(user_id)
    if not cred:
        return None
    return build('drive', 'v3', credentials=cred, cache_discovery=False)
