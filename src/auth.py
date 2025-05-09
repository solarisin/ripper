import json
import logging
import enum

import keyring
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from PySide6.QtCore import QObject, Signal

DEFAULT_TOKEN_USER = 'default-user'
TOKEN_KEY = 'ripper-gsheets'
OAUTH_CLIENT_KEY = 'ripper-oauth-client'
OAUTH_CLIENT_USER = 'default-user'
SCOPES = ['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.readonly']

log = logging.getLogger("ripper:auth")

class AuthState(enum.Enum):
    NO_CLIENT = 0
    NOT_LOGGED_IN = 1
    LOGGED_IN = 2

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


class AuthManager(QObject):
    """Manages authentication state and provides signals for state changes"""
    authStateChanged = Signal(AuthState, str)  # Signal emitted when auth state changes (state, user_email)

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AuthManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._current_state = None
        self._user_email = ""
        self._initialized = True

        # Initialize state
        self.update_auth_state()

    def get_user_info(self, cred):
        userinfo = None
        try:
            user_info_service = self.create_userinfo_service(cred)
            userinfo = user_info_service.userinfo().get().execute()
        except RefreshError as e:
            log.error(f"Failed to get user info: {e}")
        return userinfo


    def update_auth_state(self):
        """Update the current authentication state"""
        log.debug("Updating auth state")
        client_id, client_secret = get_client_credentials()

        if not client_id or not client_secret:
            new_state = AuthState.NO_CLIENT
            user_email = ""
            log.debug("No OAuth client configured")
        else:
            # Check if user is logged in
            token = keyring.get_password(TOKEN_KEY, DEFAULT_TOKEN_USER)
            if token:
                cred = Credentials.from_authorized_user_info(json.loads(token), SCOPES)
                if cred and cred.valid:
                    new_state = AuthState.LOGGED_IN
                    # get uer info
                    user_info = self.get_user_info(cred)
                    if user_info:
                        log.debug(f"User info: {user_info}")
                    user_email = cred.id_token.get('email', 'Unknown') if hasattr(cred, 'id_token') and cred.id_token else "Authenticated"
                    log.debug(f"User {user_email} is logged in")
                else:
                    new_state = AuthState.NOT_LOGGED_IN
                    user_email = ""
                    log.debug("Credentials valid - user is not logged in")
            else:
                new_state = AuthState.NOT_LOGGED_IN
                user_email = ""
                log.debug("No credentials found - user is not logged in")

        # Only emit signal if state has changed
        if new_state != self._current_state or user_email != self._user_email:
            self._current_state = new_state
            self._user_email = user_email
            log.debug(f"Auth state changed to {new_state} ({user_email})")
            self.authStateChanged.emit(new_state, user_email)

    def get_current_state(self):
        """Get the current authentication state"""
        return self._current_state, self._user_email

    def authorize(self, user_id=DEFAULT_TOKEN_USER):
        log.debug(f"Attempting to authorize user {user_id}")
        cred = None
        token = keyring.get_password(TOKEN_KEY, user_id)
        if token:
            token_json = json.loads(token)
            log.debug(f"token_json = {token_json}")
            if 'scopes' in token_json and token_json['scopes'] != SCOPES:
                log.warning(f"Token scopes do not match expected - invalidating token.")
                cred = None
            else:
                cred = Credentials.from_authorized_user_info(token_json)
        if cred and cred.expired and cred.refresh_token:
            log.debug(f"Existing expired token found - attempting to refresh")
            try:
                cred.refresh(Request())
                if cred.valid:
                    log.debug(f"Expired token successfully refreshed")
                    keyring.set_password(TOKEN_KEY, user_id, cred.to_json())
                else:
                    log.debug(f"Expired token still invalid after refresh")
            except RefreshError as e:
                log.error(f"Existing token could not be refreshed: {e}")
        if not cred or not cred.valid:
            log.debug(f"Starting OAuth flow to aquire new token for user {user_id}")
            try:
                client_config = create_client_config()
                if not client_config:
                    raise ValueError("OAuth client configuration is invalid.")
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                # TODO customize prompt and success oauth messages
                cred = flow.run_local_server(port=0)
            except ValueError as e:
                log.error(f"OAuth flow failed with error: {e}")
                # Update auth state after failed authorization
                self.update_auth_state()
                return None
            keyring.set_password(TOKEN_KEY, user_id, cred.to_json())
            log.debug(f"New OAuth token successfully created")
        else:
            log.debug(f"Previous token found and successfully authorized for user {user_id}.")

        # Update auth state after authorization
        self.update_auth_state()
        return cred

    def create_sheets_service(self, user_id=DEFAULT_TOKEN_USER):
        cred = self.authorize(user_id)
        if not cred:
            return None
        return build('sheets', 'v4', credentials=cred, cache_discovery=False)

    def create_drive_service(self, user_id=DEFAULT_TOKEN_USER):
        cred = self.authorize(user_id)
        if not cred:
            return None
        return build('drive', 'v3', credentials=cred, cache_discovery=False)

    def create_userinfo_service(self, cred=None, user_id=DEFAULT_TOKEN_USER):
        if not cred:
            cred = self.authorize(user_id)
        if not cred:
            return None
        return build('oauth2', 'v2', credentials=cred, cache_discovery=False)

# Create a singleton instance
auth_manager = AuthManager()


