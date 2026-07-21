"""
Authentication and OAuth management for the ripper project.

This module provides:
- AuthState enum and AuthInfo container for authentication state
- TokenStore for secure token and user info storage via keyring
- AuthManager singleton for managing authentication, credentials, and Google API service objects
- Integration with Qt signals for GUI updates
"""

import enum
import json
import os

import keyring
from beartype.typing import Any, Dict, List, Optional, Tuple, Type, cast
from google.auth.exceptions import GoogleAuthError, RefreshError, ResponseError, TransportError
from google.auth.exceptions import TimeoutError as GoogleAuthTimeoutError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
from googleapiclient.discovery import Resource, build
from keyring.errors import PasswordDeleteError
from loguru import logger
from PySide6.QtCore import QObject, Signal

from ripper.ripperlib.defs import DriveService, SheetsService, UserInfoService

OAUTH_CLIENT_KEY = "ripper-oauth-client"
OAUTH_CLIENT_USER = "default-user"
# Cap how long the local OAuth redirect server waits so a stalled sign-in (browser closed, no
# redirect) can't block the flow indefinitely.
OAUTH_FLOW_TIMEOUT_SECONDS = 300
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class MissingScopesError(ValueError):
    """Raised when a stored token is missing one or more required OAuth scopes.

    Subclasses ValueError so existing ``except ValueError`` handlers keep catching it. It replaces
    the previous misuse of the builtin ``SystemError`` (which is reserved for interpreter-internal
    failures) for this domain condition.
    """


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

    Holds the current authentication state and user information
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

    Handles the storage and retrieval of OAuth tokens and user information
    using the system keyring.
    """

    TOKEN_KEY = "ripper-app-auth-token"
    USERINFO_KEY = "ripper-app-auth-userinfo"
    DEFAULT_TOKEN_USER = "default-user"

    def __init__(self) -> None:
        self._current_token: Optional[str] = None
        self._current_userinfo: Optional[str] = None
        self._token_user_id: str = self.DEFAULT_TOKEN_USER  # TODO: implement multi-user support

    def invalidate(self) -> None:
        """
        Clear the current token and erase entry from keyring.

        Side effects:
            Removes token and user info from keyring for the current user.
        """
        self._current_token = None
        self._current_userinfo = None
        try:
            keyring.delete_password(self.TOKEN_KEY, self._token_user_id)
        except PasswordDeleteError:
            logger.debug(f"No token to delete for user {self._token_user_id}")

        try:
            keyring.delete_password(self.USERINFO_KEY, self._token_user_id)
        except PasswordDeleteError:
            logger.debug(f"No user info to delete for user {self._token_user_id}")

    def update_token(self, token: str) -> None:
        """
        Update only the stored token, leaving any stored user info untouched.

        Use this for a token-only rotation (e.g. a successful refresh), where the user's identity
        has not changed. `store()` is the full-identity write and treats a missing userinfo
        argument as "delete the cached user info", which would needlessly erase the cached
        email/name on every refresh (#103).

        Args:
            token (str): The OAuth token as a JSON string.

        Side effects:
            Updates the token keyring entry for the current user.
        """
        self._current_token = token
        keyring.set_password(self.TOKEN_KEY, self._token_user_id, token)
        logger.debug(f"Updated stored token for user {self._token_user_id}")

    def store(self, token: Optional[str], userinfo: Optional[str] = None) -> None:
        """
        Store token and user info in keyring.

        This is the full-identity write: `userinfo=None` means "this identity has no user info"
        and clears any previously cached entry. To rotate only the token while preserving the
        cached user info, use `update_token()` instead.

        Args:
            token (Optional[str]): The OAuth token as a JSON string, or None to invalidate.
            userinfo (Optional[str]): The user info as a JSON string, or None to remove user info.

        Side effects:
            Updates keyring entries for token and user info.
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

        logger.debug(f"Stored token for user {self._token_user_id}")

    def load(self, force: bool = False) -> Tuple[str, Optional[str]]:
        """
        Load token and user info from keyring.

        Args:
            force (bool): If True, always load from keyring even if already cached.

        Returns:
            Tuple[str, Optional[str]]: Tuple of (token, userinfo) where userinfo may be None.

        Raises:
            ValueError: If no token is found in keyring.
        """
        if self._current_token is None or force:
            self._current_token = keyring.get_password(self.TOKEN_KEY, self._token_user_id)
            self._current_userinfo = keyring.get_password(self.USERINFO_KEY, self._token_user_id)

        if self._current_token is None:
            raise ValueError("No token found in keyring.")

        return self._current_token, self._current_userinfo

    def get_credentials(self, scopes: Optional[List[str]] = None) -> Credentials:
        """
        Get credentials from the stored token.

        Args:
            scopes: List of scopes to use (optional)

        Returns:
            Credentials object
        """
        if scopes is None:
            scopes = SCOPES

        token, _ = self.load()
        token_json = json.loads(token)

        if "scopes" not in token_json or any(s not in token_json["scopes"] for s in scopes):
            raise MissingScopesError("Required scopes are missing from token.")

        return cast(Credentials, Credentials.from_authorized_user_info(token_json, scopes))

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """
        Get user info from the stored user info JSON.

        Returns:
            Dictionary of user info, or None if not available
        """
        if self._current_userinfo is None:
            return None
        try:
            return cast(Dict[str, Any], json.loads(self._current_userinfo))
        except json.JSONDecodeError as e:
            # The only expected failure here is a corrupt/non-JSON userinfo entry in the keyring;
            # treat it as "no user info" rather than masking arbitrary bugs behind a bare except.
            logger.warning(f"Stored user info is not valid JSON, ignoring it: {e}")
            return None


class AuthManager(QObject):
    """
    Singleton manager for authentication state, credentials, and Google API service objects.

    Provides Qt signals for state changes and manages token storage, credential loading,
    and user info updates for the ripper application.
    """

    authStateChanged = Signal(AuthInfo)  # Signal emitted when auth state changes

    _initialized: bool = False
    _instance: Optional["AuthManager"] = None

    def __new__(cls: Type["AuthManager"]) -> "AuthManager":
        """Create or return the singleton instance."""
        if cls._instance is None:
            cls._instance = super(AuthManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """Initialize the auth manager."""
        if self._initialized:
            return
        super().__init__(parent)
        self._current_auth_info = AuthInfo(AuthState.NO_CLIENT)
        self._initialized = True
        self._credentials: Optional[Credentials] = None
        self._token_store = TokenStore()
        self._sheets_service: Optional[SheetsService] = None
        self._drive_service: Optional[DriveService] = None
        self._oauth2_service: Optional[UserInfoService] = None
        # Credentials are persisted only in the system keyring (see TokenStore); load them at
        # startup via check_stored_credentials(). No plaintext token file is written or read (#31).

    def _get_client_secret_path(self) -> str:
        """
        Get the path to the client secret file.

        Returns:
            str: Path to the client secret file.
        """
        return os.path.join(os.environ.get("APPDATA", ""), "ripper", "client_secret.json")

    def has_oauth_client_credentials(self) -> bool:
        """Check if we have OAuth client credentials stored"""
        client_id, client_secret = self.load_oauth_client_credentials()
        return client_id is not None and client_secret is not None

    def load_oauth_client_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """Load client ID and secret from keyring.

        This is a pure read: it must not transition auth state or emit ``authStateChanged`` (#50).
        The NOT_LOGGED_IN transition that used to live here happens at the imperative call sites
        instead - store_oauth_client_credentials() when a client is configured, and
        check_stored_credentials() at startup.
        """
        oauth_client_credentials = keyring.get_password(OAUTH_CLIENT_KEY, OAUTH_CLIENT_USER)
        client_id = None
        client_secret = None
        if oauth_client_credentials:
            oauth_client_credentials_dict = json.loads(oauth_client_credentials)
            client_id = oauth_client_credentials_dict.get("client_id", "")
            client_secret = oauth_client_credentials_dict.get("client_secret", "")
        return client_id, client_secret

    def store_oauth_client_credentials(self, client_id: str, client_secret: str) -> None:
        """Store client ID and secret in keyring"""
        if not client_id or not client_secret:
            return
        self.update_state(AuthState.NOT_LOGGED_IN, override=False)
        oauth_client_credentials = {"client_id": client_id, "client_secret": client_secret}
        keyring.set_password(OAUTH_CLIENT_KEY, OAUTH_CLIENT_USER, json.dumps(oauth_client_credentials))

    @staticmethod
    def oauth_client_credentials_from_json(client_secret_json_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract client credentials from a JSON file."""
        with open(client_secret_json_path, "r") as f:
            client_data = json.load(f)
        client_id = None
        client_secret = None
        if "installed" in client_data:
            client_id = client_data["installed"].get("client_id")
            client_secret = client_data["installed"].get("client_secret")
        return client_id, client_secret

    def auth_info(self) -> AuthInfo:
        """Get the current authentication info."""
        return self._current_auth_info

    def update_state(
        self, new_state: AuthState, user_info: Optional[Dict[str, Any]] = None, *, override: bool = True
    ) -> None:
        """Update auth state and emit signal"""
        current_state = self._current_auth_info.auth_state()
        logger.debug(f"Called update_state - current: {current_state} new: {new_state} override: {override}")
        if new_state == AuthState.LOGGED_IN and user_info is None:
            # Reachable on offline startup: a valid stored token but no obtainable user info (cached
            # entry absent and the live lookup failed). Rather than raising - which crashed startup -
            # degrade to NOT_LOGGED_IN so the app comes up logged out (#50).
            logger.warning("LOGGED_IN requested without user info; degrading to NOT_LOGGED_IN")
            new_state = AuthState.NOT_LOGGED_IN
        if new_state == current_state:
            return
        if new_state > current_state or override:
            logger.debug(f"Updating auth state to {new_state}")
            self._current_auth_info = AuthInfo(new_state, user_info)
            self.authStateChanged.emit(self._current_auth_info)

    def clear_stored_credentials(self) -> None:
        """Clear the stored credentials."""
        self._token_store.invalidate()

    def retrieve_user_info(self, cred: Credentials) -> Optional[Dict[str, Any]]:
        """
        Retrieve user info using the provided credentials.

        Args:
            cred: OAuth2 credentials

        Returns:
            Dictionary containing user information, or None if retrieval fails
        """
        try:
            user_info_service = self.create_userinfo_service(cred)
            if user_info_service:
                result = cast(Dict[str, Any], user_info_service.userinfo().get().execute())
                return result
            return None
        except RefreshError as e:
            logger.error(f"Failed to get user info: {e}")
            return None

    def refresh_token(self, expired_cred: Credentials) -> Optional[Credentials]:
        """
        Attempt to refresh expired credentials.

        Args:
            expired_cred: Expired credentials to refresh

        Returns:
            Refreshed credentials if successful, None otherwise. Transient failures - transport
            errors (offline, DNS, timeout) and retryable server errors (500/503 from the token
            endpoint, RefreshError with retryable=True) - return None but leave the stored
            token/user info in the keyring so the next launch can refresh silently; only
            non-retryable credential failures (e.g. an invalid/revoked refresh token)
            invalidate the store.
        """
        if expired_cred.refresh_token:
            try:
                expired_cred.refresh(Request())
                if expired_cred.valid:
                    valid_cred = expired_cred
                    logger.debug("Expired token successfully refreshed")
                    # Token-only update: the user's identity is unchanged, so the cached user
                    # info must survive the refresh (#103).
                    self._token_store.update_token(valid_cred.to_json())
                    return valid_cred
                else:
                    logger.debug("Expired credentials still invalid after refresh - invalidating token")
            except (TransportError, GoogleAuthTimeoutError, ResponseError) as ex:
                # Transient network-layer failures: the sync transport wraps offline/DNS/SSL/
                # timeout errors in TransportError (TimeoutError/ResponseError cover the other
                # transports). The credentials were never rejected, so keep them stored and
                # degrade to logged-out for this session only (#102).
                logger.warning(
                    f"Could not refresh credentials due to a network error; keeping stored token - "
                    f"{type(ex).__name__}: {ex}"
                )
                return None
            except GoogleAuthError as ex:
                if ex.retryable:
                    # google-auth marks retryable HTTP failures from the token endpoint
                    # (500/503, server_error, temporarily_unavailable) with retryable=True
                    # after its internal retries are exhausted. Environmental, not a rejected
                    # token - keep the stored credentials for the next launch (#102).
                    logger.warning(
                        f"Could not refresh credentials due to a retryable server error; keeping "
                        f"stored token - {type(ex).__name__}: {ex}"
                    )
                    return None
                # Credential-layer failures (RefreshError for an invalid/revoked/expired refresh
                # token, ReauthFailError, etc.): the token is no longer usable, so invalidate it.
                logger.error(
                    f"Existing credentials could not be refreshed, token will be invalidated - "
                    f"{type(ex).__name__}: {ex}"
                )
        self._token_store.invalidate()
        return None

    def attempt_load_stored_token(self) -> Optional[Credentials]:
        """
        Attempt to load and validate stored token.

        Returns:
            Valid credentials if successful, None otherwise
        """
        try:
            stored_cred: Optional[Credentials] = self._token_store.get_credentials()
            logger.debug("Found existing token")
            if stored_cred and stored_cred.expired:
                logger.debug("Existing token is expired, attempting refresh")
                stored_cred = self.refresh_token(stored_cred)
            return stored_cred
        except MissingScopesError as e:
            # More specific than ValueError (its base), so it must be caught first.
            logger.error(f"Existing token is invalid, please re-authorize: {e}")
            return None
        except ValueError as e:
            logger.error(e)
            return None

    def acquire_new_credentials(self) -> Optional[Credentials]:
        """
        Start the OAuth flow to acquire a new token.

        Returns:
            Credentials object if successful, None otherwise
        """
        logger.debug("Starting OAuth flow to acquire new token")
        client_id, client_secret = self.load_oauth_client_credentials()
        if not (client_id and client_secret):
            logger.error("OAuth client configuration is invalid.")
            self.update_state(AuthState.NO_CLIENT)
            return None

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uris": ["http://localhost"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        try:
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            # timeout_seconds bounds the local redirect server's wait, so an abandoned sign-in
            # (browser closed, no redirect) fails instead of hanging forever.
            creds = flow.run_local_server(port=0, timeout_seconds=OAUTH_FLOW_TIMEOUT_SECONDS)
            return cast(Credentials, creds)
        except Exception as e:
            # run_local_server can raise a wide range of failures — a redirect timeout, socket/OS
            # errors, RefreshError, or the user closing the browser. None must propagate uncaught
            # into the create_*_service / UI path, where it would freeze or crash the app. The
            # client is configured (checked above), so this is a login failure, not a missing client.
            logger.error(f"OAuth flow failed: {e}")
            self.update_state(AuthState.NOT_LOGGED_IN)
            return None

    def check_stored_credentials(self) -> None:
        """Check and update state based on stored credentials."""
        logger.debug("Updating state based on stored credentials")
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

            if user_info:
                self._credentials = stored_cred
                self.update_state(AuthState.LOGGED_IN, user_info)
            else:
                # Valid stored token but no obtainable user info (e.g. offline startup). Caching
                # stored_cred here would let the next authorize() short-circuit and return a usable
                # credential under a logged-out state, so leave _credentials unset - authorize()
                # then retries user-info recovery. The stored keyring token is preserved: this is a
                # transient profile-fetch failure, not a token rejection (#103/#50).
                self._credentials = None
                self.update_state(AuthState.NOT_LOGGED_IN)
        else:
            self.update_state(AuthState.NOT_LOGGED_IN)

    def authorize(self, *, force: bool = False, silent: bool = False) -> Optional[Credentials]:
        """
        Attempt to authorize with Google OAuth.

        Args:
            force: If True, force re-authentication even if credentials exist
            silent: If True, suppress user interaction

        Returns:
            Credentials object if successful, None otherwise
        """
        logger.debug("Attempting to authorize")
        if self._credentials and not force:
            logger.debug("Using cached credentials")
            return self._credentials
        user_info = None
        credentials: Optional[Credentials] = None
        if not force:
            credentials = self.attempt_load_stored_token()
        if not credentials:
            if silent:
                # A silent authorize is a non-interactive "still logged in?" check: no usable
                # cached/stored credential was obtainable, so refuse to open the browser via
                # acquire_new_credentials() and report not-authorized. Leave state consistent with
                # the invariant LOGGED_IN <=> user_info present <=> _credentials usable - no
                # half-set credential, logged-out - exactly like the interactive failure path (#106).
                logger.debug("No stored credentials available; skipping interactive auth (silent)")
                self._credentials = None
                self.update_state(AuthState.NOT_LOGGED_IN)
                return None
            credentials = self.acquire_new_credentials()
            if credentials:
                user_info = self.retrieve_user_info(credentials)
                self._token_store.store(credentials.to_json(), json.dumps(user_info) if user_info else None)
        else:
            logger.debug("Previous token found and successfully authorized.")
        if not credentials:
            logger.debug("Failed to authorize")
            self.update_state(AuthState.NOT_LOGGED_IN)
            return None
        if user_info is None:
            user_info = self.retrieve_user_info(credentials)
        if user_info is None:
            # We hold a usable token but couldn't fetch the user profile (transient failure).
            # Invariant: LOGGED_IN <=> user_info present <=> _credentials usable. Presenting a
            # credential here would let create_*_service() build authenticated clients while
            # auth_info says NOT_LOGGED_IN, and caching it would make the next authorize()
            # short-circuit past user-info recovery. So retain nothing usable and report failure;
            # the caller retries next time. The stored keyring token is deliberately left intact
            # (a profile-fetch failure is not a token rejection - #103), so a later attempt can
            # succeed without a fresh OAuth flow. (#50)
            logger.warning("Authorized a token but user info is unavailable; staying logged out and not caching it")
            self._credentials = None
            self.update_state(AuthState.NOT_LOGGED_IN)
            return None
        logger.info(f"Authorization successful. User {user_info} logged in.")
        self._credentials = credentials
        self.update_state(AuthState.LOGGED_IN, user_info)
        return credentials

    # Service creation methods

    def create_sheets_service(self) -> Optional[SheetsService]:
        """
        Create an authenticated Google Sheets API service.

        Returns:
            Google Sheets API service instance, or None if authentication fails
        """
        cred = self.authorize()
        if not cred:
            return None
        service = build("sheets", "v4", credentials=cred)
        return cast(SheetsService, cast(Resource, service))

    def create_drive_service(self) -> Optional[DriveService]:
        """
        Create an authenticated Google Drive API service.

        Returns:
            Google Drive API service instance, or None if authentication fails
        """
        cred = self.authorize()
        if not cred:
            return None
        service = build("drive", "v3", credentials=cred)
        return cast(DriveService, cast(Resource, service))

    def create_userinfo_service(self, cred: Optional[Credentials] = None) -> Optional[UserInfoService]:
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
        service = build("oauth2", "v2", credentials=cred)
        return cast(UserInfoService, cast(Resource, service))
