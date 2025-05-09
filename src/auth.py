import json
import logging
import enum
from json.decoder import JSONObject

import keyring
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from PySide6.QtCore import QObject, Signal
from shiboken6.Shiboken import invalidate

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

class AuthInfo:
    def __init__(self, state=AuthState.NO_CLIENT, info=None):
        self._auth_state = state
        self._user_info = info


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
    authStateChanged = Signal(AuthInfo)  # Signal emitted when auth state changes

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AuthManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, parent=None):
        if self._initialized:
            return
        super().__init__(parent)
        self._current_state = AuthState.NO_CLIENT
        self._token_user_id = DEFAULT_TOKEN_USER
        self._user_info = None
        self._initialized = True
        self._credentials = None

    def get_user_info(self, cred):
        userinfo = None
        try:
            user_info_service = self.create_userinfo_service(cred)
            userinfo = user_info_service.userinfo().get().execute()
        except RefreshError as e:
            log.error(f"Failed to get user info: {e}")
        return userinfo

    def invalidate_credentials(self):
        self._credentials = None
        keyring.delete_password(TOKEN_KEY, self._token_user_id)

    def store_credentials(self, cred):
        if cred is None:
            self.invalidate_credentials()
            return
        self._credentials = cred
        keyring.set_password(TOKEN_KEY, self._token_user_id, cred.to_json())

    def get_credentials(self, *, load_if_none=False):
        if self._credentials is None and load_if_none:
            return self.load_credentials()
        return self._credentials

    def load_credentials(self, *, new_token=None):
        cred_loaded = None
        if new_token:
            token_json = new_token.to_json()
        else:
            token_json = keyring.get_password(TOKEN_KEY, self._token_user_id)
        if token_json:
            cred_loaded = Credentials.from_authorized_user_info(token_json)

        // TODO

        self._credentials = cred_loaded
        return cred_loaded

    def refresh_token(self, expired_cred):
        valid_cred = None
        if expired_cred.refresh_token:
            try:
                expired_cred.refresh(Request())
                if expired_cred.valid:
                    valid_cred = expired_cred
                    log.debug("Expired token successfully refreshed")
                    self.store_credentials(valid_cred)
                    return valid_cred
                else:
                    log.debug("Expired token still invalid after refresh - invalidating credentials")
            except RefreshError as ex:
                log.error(f"Existing token could not be refreshed and will be invalidated - error: {ex}")
        self.invalidate_credentials()
        return None


    def attempt_load_stored_token(self):
        """
        Check keyring for a matching TOKEN_KEY and user_id. If one exists, ensure the scopes
          match the currently configured SCOPES variable. If so, refresh the token if required, then
          return the valid credentials.  Otherwise, None is returned.
        """
        stored_cred = None
        token = self.get_credentials(authorize_if_none=False)
        if token:
            log.debug(f"Found existing token for user '{self._token_user_id}'")
            token_json = token.to_json()
            if 'scopes' in token_json and token_json['scopes'] != SCOPES:
                log.warning(f"Stored token scopes are outdated - invalidating credentials.")
                self.invalidate_credentials()
            else:
                stored_cred = self.load_credentials()
                if stored_cred.expired:
                    log.debug(f"Existing token for user '{self._token_user_id}' expired, attempting refresh")
                    stored_cred = self.refresh_token(stored_cred)
                if stored_cred.invalid:
                    log.warning("Token not valid - invalidating credentials")
                    stored_cred = None
                    self.invalidate_credentials()
        return stored_cred


    def acquire_new_credentials(self):
        log.debug(f"Starting OAuth flow to acquire new token for user {self._token_user_id}")
        try:
            client_config = create_client_config()
            if not client_config:
                raise ValueError("OAuth client configuration is invalid.")
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            # TODO customize prompt and success oauth messages
            cred = flow.run_local_server(port=0)
        except ValueError as e:
            log.error(f"OAuth flow failed with error: {e}")
            self.authStateChanged.emit(AuthState.NO_CLIENT, None)
            return None
        self.store_credentials(cred)
        log.debug(f"New OAuth token successfully created")
        return cred

    def authorize(self, user_id=DEFAULT_TOKEN_USER):

        log.debug(f"Attempting to authorize user {self._token_user_id}")

        # Attempt to load any stored credentials for this user
        cred = self.attempt_load_stored_token()
        if not cred:
            cred = self.acquire_new_credentials()
        else:
            log.debug(f"Previous token found and successfully authorized for user {user_id}.")

        self._user_info = self.get_user_info(cred)

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


