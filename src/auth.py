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
from shiboken6.Shiboken import invalidate


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


class TokenStore:
    """Manages token storage and retrieval through keyring"""
    TOKEN_KEY = 'ripper-app'
    DEFAULT_TOKEN_USER = 'default-user'

    def __init__(self):
        self._current_token = None
        self._token_user_id:str = self.DEFAULT_TOKEN_USER  # TODO multi-user support

    def invalidate(self):
        """Clear the current token and erase entry from keyring"""
        self._current_token = None
        keyring.delete_password(self.TOKEN_KEY, self._token_user_id)

    def store(self, token):
        if token is None:
            self.invalidate()
            return
        self._current_token = token
        keyring.set_password(self.TOKEN_KEY, self._token_user_id, token)

    def load(self, force=False):
        if self._current_token is None or force:
            self._current_token = keyring.get_password(self.TOKEN_KEY, self._token_user_id)
        if self._current_token is None:
            raise ValueError("No token found in keyring.")
        return self._current_token

    def get_credentials(self, scopes=None):
        """Get OAuth2 credentials from stored token.
    
        Args:
            scopes (list, optional): List of OAuth scopes to validate against stored token.
                                   If None, uses default SCOPES. Defaults to None.
    
        Returns:
            Credentials: Google OAuth2 credentials object created from stored token.
    
        Raises:
            ValueError: If no token is found in keyring.
            SystemError: If required scopes are missing from stored token.
        """

        if scopes is None:
            scopes = SCOPES
        token = self.load()
        if 'scopes' not in token or any([s for s in scopes if s not in token['scopes']]):
            raise SystemError("Required scopes are missing from token.")
        return Credentials.from_authorized_user_info(token)


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
        self._user_info = None
        self._initialized = True
        self._credentials = None
        self._token_store = TokenStore()


    def get_user_info(self, cred):
        userinfo = None
        try:
            user_info_service = self.create_userinfo_service(cred)
            userinfo = user_info_service.userinfo().get().execute()
        except RefreshError as e:
            log.error(f"Failed to get user info: {e}")
        return userinfo


    def refresh_token(self, expired_cred):
        if expired_cred.refresh_token:
            try:
                expired_cred.refresh(Request())
                if expired_cred.valid:
                    valid_cred = expired_cred
                    log.debug("Expired token successfully refreshed")
                    self._token_store.store(valid_cred.to_json())
                    return valid_cred
                else:
                    log.debug("Expired credentials still invalid after refresh - invalidating token")
            except RefreshError as ex:
                log.error(f"Existing credentials could not be refreshed, token will be invalidated - error: {ex}")
        self._token_store.invalidate()
        return None


    def attempt_load_stored_token(self):
        try:
            stored_cred = self._token_store.get_credentials()
            log.debug(f"Found existing token")
            if stored_cred.expired:
                log.debug(f"Existing token is expired, attempting refresh")
                stored_cred = self.refresh_token(stored_cred)
        except ValueError as e:
            log.error(f"No token found in keyring: {e}")
            stored_cred = None
        except SystemError as e:
            log.error(f"Existing token is invalid, please re-authorize: {e}")
            stored_cred = None
        return stored_cred


    def acquire_new_credentials(self):
        log.debug(f"Starting OAuth flow to acquire new token")
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
        self._token_store.store(cred.to_json())
        log.debug(f"New OAuth token successfully created")
        return cred


    def authorize(self):
        log.debug(f"Attempting to authorize")

        # Attempt to load any stored credentials for this user
        cred = self.attempt_load_stored_token()
        if not cred:
            cred = self.acquire_new_credentials()
        else:
            log.debug(f"Previous token found and successfully authorized.")

        self._user_info = self.get_user_info(cred)
        return cred

    def create_sheets_service(self):
        cred = self.authorize()
        if not cred:
            return None
        return build('sheets', 'v4', credentials=cred, cache_discovery=False)

    def create_drive_service(self):
        cred = self.authorize()
        if not cred:
            return None
        return build('drive', 'v3', credentials=cred, cache_discovery=False)

    def create_userinfo_service(self, cred=None):
        if not cred:
            cred = self.authorize()
        if not cred:
            return None
        return build('oauth2', 'v2', credentials=cred, cache_discovery=False)

# Create a singleton instance
auth_manager = AuthManager()

# TODO re=implement status signal
