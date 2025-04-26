import os
import json
import keyring
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from database import insert_login_attempt

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
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.error(f"Error refreshing credentials: {e}")
                insert_login_attempt(success=False)
                raise Exception(f"Error refreshing credentials: {e}")
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            except Exception as e:
                logging.error(f"Error during authentication flow: {e}")
                insert_login_attempt(success=False)
                raise Exception(f"Error during authentication flow: {e}")
        
        keyring.set_password(TOKEN_KEY, 'user', creds.to_json())
    
    insert_login_attempt(success=True)
    return creds
