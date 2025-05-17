import enum
import json
import logging
import keyring
from json import JSONDecodeError
from typing import Dict, List, Optional, Any, Tuple
from PySide6.QtCore import QObject, Signal
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from keyring.errors import PasswordDeleteError

OAUTH_CLIENT_KEY = "ripper-oauth-client"
OAUTH_CLIENT_USER = "default-user"
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

log = logging.getLogger("ripper:auth")


class AuthState(enum.Enum):
    """
    Enumeration of possible authentication states.

    States are ordered from least authenticated to most authenticated:
    - NO_CLIENT: No OAuth client credentials are configured
    - NOT_LOGGED_IN: OAuth client is configured but user is not logged in
    - LOGGED_IN: User is fully authenticated
    """

    NO_CLIENT = 0
    NOT_LOGGED_IN = 1
    LOGGED_IN = 2

    def __lt__(self, other: "AuthState") -> bool:
        """Compare if this state is less authenticated than another state."""
        if self.__class__ is other.__class__:
            return self.value < other.value
        return NotImplemented

    def __gt__(self, other: "AuthState") -> bool:
        """Compare if this state is more authenticated than another state."""
        if self.__class__ is other.__class__:
            return self.value > other.value
        return NotImplemented


class AuthInfo:
    """
    Container for authentication state and user information.

    This class holds the current authentication state and user information
    and provides methods to access them.
    """

    def __init__(self, state: AuthState = AuthState.NO_CLIENT, info: Optional[Dict[str, Any]] = None):
        """
        Initialize with authentication state and user information.

        Args:
            state: The authentication state
            info: Dictionary containing user information
        """
        self._state: AuthState = state
        self._user_info: Optional[Dict[str, Any]] = info

    def auth_state(self) -> AuthState:
        """
        Get the current authentication state.

        Returns:
            The current authentication state
        """
        return self._state

    def user_email(self) -> Optional[str]:
        """
        Get the user's email address if available.

        Returns:
            The user's email address, or None if not available
        """
        if self._user_info is None:
            return None
        return self._user_info.get("email")


class TokenStore:
    """
    Manages token storage and retrieval through keyring.

    This class handles the storage and retrieval of OAuth tokens and user information
    using the system keyring.
    """

    TOKEN_KEY = "ripper-app-auth-token"
    USERINFO_KEY = "ripper-app-auth-userinfo"
    DEFAULT_TOKEN_USER = "default-user"

    def __init__(self):
        self._current_token: Optional[str] = None
        self._current_userinfo: Optional[str] = None
        self._token_user_id: str = self.DEFAULT_TOKEN_USER  # TODO: implement multi-user support

    def invalidate(self) -> None:
        """
        Clear the current token and erase entry from keyring.
        """
        self._current_token = None
        self._current_userinfo = None
        try:
            keyring.delete_password(self.TOKEN_KEY, self._token_user_id)
        except PasswordDeleteError:
            log.debug(f"No token to delete for user {self._token_user_id}")

        try:
            keyring.delete_password(self.USERINFO_KEY, self._token_user_id)
        except PasswordDeleteError:
            log.debug(f"No user info to delete for user {self._token_user_id}")

    def store(self, token: Optional[str], userinfo: Optional[str] = None) -> None:
        """
        Store token and user info in keyring.

        Args:
            token: The OAuth token as a JSON string, or None to invalidate
            userinfo: The user info as a JSON string, or None to remove user info
        """
        if token is None:
            self.invalidate()
            return

        self._current_token = token
        keyring.set_password(self.TOKEN_KEY, self._token_user_id, token)

        if userinfo is not None:
            self._current_userinfo = userinfo
            keyring.set_password(self.USERINFO_KEY, self._token_user_id, userinfo)
        else:
            try:
                self._current_userinfo = None
                keyring.delete_password(self.USERINFO_KEY, self._token_user_id)
            except PasswordDeleteError:
                pass

        log.debug(f"Stored token for user {self._token_user_id}")

    def load(self, force: bool = False) -> Tuple[str, Optional[str]]:
        """
        Load token and user info from keyring.

        Args:
            force: If True, always load from keyring even if already cached

        Returns:
            Tuple of (token, userinfo) where userinfo may be None

        Raises:
            ValueError: If no token is found in keyring
        """
        if self._current_token is None or force:
            self._current_token = keyring.get_password(self.TOKEN_KEY, self._token_user_id)
            self._current_userinfo = keyring.get_password(self.USERINFO_KEY, self._token_user_id)

        if self._current_token is None:
            raise ValueError("No token found in keyring.")

        return self._current_token, self._current_userinfo

    def get_credentials(self, scopes: Optional[List[str]] = None) -> Credentials:
        """
        Get OAuth2 credentials from stored token.

        Args:
            scopes: List of OAuth scopes to validate against stored token.
                   If None, uses default SCOPES.

        Returns:
            Google OAuth2 credentials object created from stored token.

        Raises:
            ValueError: If no token is found in keyring.
            SystemError: If required scopes are missing from stored token.
        """
        if scopes is None:
            scopes = SCOPES

        token, _ = self.load()
        token_json = json.loads(token)

        if "scopes" not in token_json or any(s for s in scopes if s not in token_json["scopes"]):
            raise SystemError("Required scopes are missing from token.")

        return Credentials.from_authorized_user_info(token_json)

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """
        Get user info associated with stored token.

        Returns:
            Dictionary containing user information, or None if not available
        """
        try:
            _, userinfo = self.load()
            if userinfo is None:
                return None

            return json.loads(userinfo)

        except JSONDecodeError as e:
            stored_userinfo = self._current_userinfo or "None"
            log.error(f"Stored user info json was malformed. {e}: {stored_userinfo}")
            self._current_userinfo = None

            try:
                keyring.delete_password(self.USERINFO_KEY, self._token_user_id)
            except PasswordDeleteError:
                pass

            return None

        except Exception as e:
            log.error(f"Failed to load stored user info: {repr(e)}")
            return None


class AuthManager(QObject):
    """Manages authentication state and provides signals for state changes."""

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
        self._current_auth_info = AuthInfo(AuthState.NO_CLIENT)
        self._initialized = True
        self._credentials = None
        self._token_store = TokenStore()

    def has_oauth_client_credentials(self):
        """Check if we have OAuth client credentials stored"""
        client_id, client_secret = self.load_oauth_client_credentials()
        return client_id is not None and client_secret is not None

    def load_oauth_client_credentials(self):
        """Load client ID and secret from keyring"""
        oauth_client_credentials = keyring.get_password(OAUTH_CLIENT_KEY, OAUTH_CLIENT_USER)
        client_id = None
        client_secret = None
        if oauth_client_credentials:
            oauth_client_credentials_dict = json.loads(oauth_client_credentials)
            client_id = oauth_client_credentials_dict.get("client_id", "")
            client_secret = oauth_client_credentials_dict.get("client_secret", "")
            self.update_state(AuthState.NOT_LOGGED_IN, override=False)
        return client_id, client_secret

    def store_oauth_client_credentials(self, client_id, client_secret):
        """Store client ID and secret in keyring"""
        if not client_id or not client_secret:
            return
        self.update_state(AuthState.NOT_LOGGED_IN, override=False)
        oauth_client_credentials = {"client_id": client_id, "client_secret": client_secret}
        keyring.set_password(OAUTH_CLIENT_KEY, OAUTH_CLIENT_USER, json.dumps(oauth_client_credentials))

    @staticmethod
    def oauth_client_credentials_from_json(client_secret_json_path):
        with open(client_secret_json_path, "r") as f:
            client_data = json.load(f)
        client_id = None
        client_secret = None
        # Extract client ID and secret from the file
        if "installed" in client_data:
            client_id = client_data["installed"].get("client_id")
            client_secret = client_data["installed"].get("client_secret")
        return client_id, client_secret

    def auth_info(self):
        return self._current_auth_info

    def update_state(self, new_state: AuthState, user_info=None, *, override=True):
        """Update auth state and emit signal"""
        current_state = self._current_auth_info.auth_state()
        log.debug(f"Called update_state - current: {current_state} new: {new_state} override: {override}")
        if new_state == current_state:
            return
        if new_state == AuthState.LOGGED_IN and user_info is None:
            raise ValueError("User info must be provided for logged-in state.")
        if new_state > current_state or override:
            log.debug(f"Updating auth state to {new_state}")
            self._current_auth_info = AuthInfo(new_state, user_info)
            self.authStateChanged.emit(self._current_auth_info)

    def retrieve_user_info(self, cred):
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
            log.debug("Found existing token")
            if stored_cred.expired:
                log.debug("Existing token is expired, attempting refresh")
                stored_cred = self.refresh_token(stored_cred)
        except ValueError as e:
            log.error(f"No token found in keyring: {e}")
            stored_cred = None
        except SystemError as e:
            log.error(f"Existing token is invalid, please re-authorize: {e}")
            stored_cred = None
        return stored_cred

    def acquire_new_credentials(self):
        """
        Start the OAuth flow to acquire a new token.

        Returns:
            Credentials object if successful, None otherwise
        """
        log.debug("Starting OAuth flow to acquire new token")
        try:
            client_config = None
            client_id, client_secret = self.load_oauth_client_credentials()
            if client_id and client_secret:
                client_config = {
                    "installed": {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uris": ["http://localhost"],
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                }
            if not client_config:
                raise ValueError("OAuth client configuration is invalid.")

            # Start the user oauth flow using the client config and configured scopes
            # TODO: customize prompt and success oauth messages
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

            new_credentials = flow.run_local_server(port=0)
        except ValueError as e:
            log.error(f"OAuth flow failed with error: {e}")
            # Update auth state to NO_CLIENT
            self.update_state(AuthState.NO_CLIENT)
            return None

        log.debug("New OAuth token successfully created")
        return new_credentials

    def check_stored_credentials(self):
        log.debug("Updating state based on stored credentials")
        if self._current_auth_info.auth_state() == AuthState.NO_CLIENT:
            if not self.has_oauth_client_credentials():
                self.update_state(AuthState.NO_CLIENT)
                return

        stored_cred = self.attempt_load_stored_token()
        if stored_cred:
            user_info = self._token_store.get_user_info()
            if not user_info:
                user_info = self.retrieve_user_info(stored_cred)
                if user_info:
                    self._token_store.store(stored_cred.to_json(), json.dumps(user_info))

            self._credentials = stored_cred
            self.update_state(AuthState.LOGGED_IN, user_info)
        else:
            self.update_state(AuthState.NOT_LOGGED_IN)

    def authorize(self, *, force=False, silent=False):
        log.debug("Attempting to authorize")

        # First, check if we have previously successfully authenticated and return cached credentials if so
        #  unless force is True, in which case we will re-authenticate regardless of cached credentials.
        if self._credentials and not force:
            log.debug("Using cached credentials")
            return self._credentials

        # No cached credentials, attempt to load from storage unless force is true. Otherwise,
        #  re-authenticate by starting the OAuth flow.
        user_info = None
        credentials = None
        if not force:
            credentials = self.attempt_load_stored_token()
        if not credentials:
            credentials = self.acquire_new_credentials()
            user_info = self.retrieve_user_info(credentials)

            # Store the new credentials token and userinfo
            self._token_store.store(credentials.to_json(), json.dumps(user_info))
        else:
            log.debug("Previous token found and successfully authorized.")

        if not credentials:
            log.debug("Failed to authorize")
            self.update_state(AuthState.NOT_LOGGED_IN)
            return None

        # If we are here and still don't have any user_info, we probably have just
        #  loaded credentials from storage and don't have user info yet.
        if user_info is None:
            user_info = self.retrieve_user_info(credentials)
        self._credentials = credentials
        self.update_state(AuthState.LOGGED_IN, user_info)
        return credentials

    # Service creation methods

    def create_sheets_service(self):
        """
        Create an authenticated Google Sheets API service.

        Returns:
            Google Sheets API service instance, or None if authentication fails
        """
        cred = self.authorize()
        if not cred:
            return None
        return build("sheets", "v4", credentials=cred, cache_discovery=False)

    def create_drive_service(self):
        """
        Create an authenticated Google Drive API service.

        Returns:
            Google Drive API service instance, or None if authentication fails
        """
        cred = self.authorize()
        if not cred:
            return None
        return build("drive", "v3", credentials=cred, cache_discovery=False)

    def create_userinfo_service(self, cred=None):
        """
        Create an authenticated Google OAuth2 userinfo API service.

        Args:
            cred: Optional credentials to use. If None, will call authorize()

        Returns:
            Google OAuth2 API service instance, or None if authentication fails
        """
        if not cred:
            cred = self.authorize()
        if not cred:
            return None
        return build("oauth2", "v2", credentials=cred, cache_discovery=False)
