import os
import json
import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
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
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        keyring.set_password(TOKEN_KEY, 'user', creds.to_json())
    
    insert_login_attempt(success=True)
    list_google_sheets(creds)
    return creds

def list_google_sheets(credentials):
    try:
        service = build('drive', 'v3', credentials=credentials)
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            pageSize=10,
            fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])

        if not items:
            print('No Google Sheets found.')
            return []
        else:
            print('Google Sheets:')
            for item in items:
                print(f"{item['name']} ({item['id']})")
            return items
    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def prompt_data_source_configuration():
    # Implement the logic to prompt the user to configure data sources
    pass
