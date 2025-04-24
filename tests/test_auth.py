import os
import json
import pytest
import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from auth import authenticate, TOKEN_KEY, CLIENT_SECRET_FILE, prompt_data_source_configuration, list_google_sheets
from database import insert_login_attempt

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

def test_authenticate_new_token(monkeypatch):
    def mock_run_local_server(self, *args, **kwargs):
        return Credentials.from_authorized_user_info({
            "token": "new_token",
            "refresh_token": "new_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "client_secret",
            "scopes": SCOPES
        })

    monkeypatch.setattr(InstalledAppFlow, "run_local_server", mock_run_local_server)
    monkeypatch.setattr(keyring, "get_password", lambda *args: None)
    monkeypatch.setattr(keyring, "set_password", lambda *args: None)

    creds = authenticate()
    assert creds.token == "new_token"
    assert creds.refresh_token == "new_refresh_token"

def test_authenticate_existing_token(monkeypatch):
    def mock_refresh(self, request):
        self.token = "refreshed_token"

    monkeypatch.setattr(Credentials, "refresh", mock_refresh)
    monkeypatch.setattr(keyring, "get_password", lambda *args: json.dumps({
        "token": "existing_token",
        "refresh_token": "existing_refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client_id",
        "client_secret": "client_secret",
        "scopes": SCOPES
    }))
    monkeypatch.setattr(keyring, "set_password", lambda *args: None)

    creds = authenticate()
    assert creds.token == "refreshed_token"
    assert creds.refresh_token == "existing_refresh_token"

def test_secure_storage(monkeypatch):
    def mock_set_password(service, username, password):
        assert service == TOKEN_KEY
        assert username == "user"
        assert json.loads(password)["token"] == "new_token"

    monkeypatch.setattr(keyring, "set_password", mock_set_password)
    monkeypatch.setattr(keyring, "get_password", lambda *args: None)
    monkeypatch.setattr(InstalledAppFlow, "run_local_server", lambda *args: Credentials.from_authorized_user_info({
        "token": "new_token",
        "refresh_token": "new_refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client_id",
        "client_secret": "client_secret",
        "scopes": SCOPES
    }))

    authenticate()

def test_prompt_data_source_configuration(monkeypatch):
    def mock_prompt_data_source_configuration():
        return True

    monkeypatch.setattr('auth.prompt_data_source_configuration', mock_prompt_data_source_configuration)
    assert prompt_data_source_configuration() == True

def test_insert_login_attempt(monkeypatch):
    def mock_insert_login_attempt(success):
        assert success == True

    monkeypatch.setattr('database.insert_login_attempt', mock_insert_login_attempt)
    insert_login_attempt(success=True)

def test_list_google_sheets(monkeypatch):
    def mock_list_google_sheets(credentials):
        return [
            {"id": "sheet1", "name": "Test Sheet 1"},
            {"id": "sheet2", "name": "Test Sheet 2"}
        ]

    monkeypatch.setattr('auth.list_google_sheets', mock_list_google_sheets)
    credentials = Credentials.from_authorized_user_info({
        "token": "test_token",
        "refresh_token": "test_refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client_id",
        "client_secret": "client_secret",
        "scopes": SCOPES
    })
    sheets = list_google_sheets(credentials)
    assert len(sheets) == 2
    assert sheets[0]["name"] == "Test Sheet 1"
    assert sheets[1]["name"] == "Test Sheet 2"

def test_authenticate_calls_list_google_sheets(monkeypatch):
    def mock_run_local_server(self, *args, **kwargs):
        return Credentials.from_authorized_user_info({
            "token": "new_token",
            "refresh_token": "new_refresh_token",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "client_id",
            "client_secret": "client_secret",
            "scopes": SCOPES
        })

    def mock_list_google_sheets(credentials):
        return [
            {"id": "sheet1", "name": "Test Sheet 1"},
            {"id": "sheet2", "name": "Test Sheet 2"}
        ]

    monkeypatch.setattr(InstalledAppFlow, "run_local_server", mock_run_local_server)
    monkeypatch.setattr('auth.list_google_sheets', mock_list_google_sheets)
    monkeypatch.setattr(keyring, "get_password", lambda *args: None)
    monkeypatch.setattr(keyring, "set_password", lambda *args: None)

    creds = authenticate()
    assert creds.token == "new_token"
    assert creds.refresh_token == "new_refresh_token"
    sheets = list_google_sheets(creds)
    assert len(sheets) == 2
    assert sheets[0]["name"] == "Test Sheet 1"
    assert sheets[1]["name"] == "Test Sheet 2"
