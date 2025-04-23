import os
import json
import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
TOKEN_KEY = 'google_sheets_token'
CLIENT_SECRET_FILE = 'client_secret.json'

def authenticate():
    creds = None
    token = keyring.get_password(TOKEN_KEY, 'user')
    if token:
        creds = Credentials.from_authorized_user_info(json.loads(token), SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        keyring.set_password(TOKEN_KEY, 'user', creds.to_json())
    
    return creds
