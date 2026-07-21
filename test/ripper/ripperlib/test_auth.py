import json
import unittest
from unittest.mock import MagicMock, create_autospec, patch

from google.auth.exceptions import GoogleAuthError, RefreshError, ResponseError, TransportError
from google.auth.exceptions import TimeoutError as GoogleAuthTimeoutError
from google.oauth2.credentials import Credentials
from keyring.errors import PasswordDeleteError

from ripper.ripperlib.auth import (
    OAUTH_CLIENT_KEY,
    OAUTH_CLIENT_USER,
    SCOPES,
    AuthInfo,
    AuthManager,
    AuthState,
    MissingScopesError,
    TokenStore,
)

# Helper: create dummy credentials
DUMMY_CREDS = Credentials(
    token="dummy-token",
    refresh_token="dummy-refresh",
    token_uri="https://oauth2.googleapis.com/token",
    client_id="dummy-client-id",
    client_secret="dummy-client-secret",
    scopes=SCOPES,
)


# Helper: create a mock Credentials with mutable properties
def make_mock_creds(expired=False, valid=True, refresh_token="test_refresh_token"):
    mock_cred = create_autospec(Credentials, instance=True)
    type(mock_cred).expired = property(lambda self: expired)
    type(mock_cred).valid = property(lambda self: valid)
    type(mock_cred).refresh_token = property(lambda self: refresh_token)
    mock_cred.to_json.return_value = json.dumps({"access_token": "new_token"})
    return mock_cred


# Helper: a stand-in for a built Google API service. A plain MagicMock is used (rather
# than create_autospec(Resource)) so it structurally satisfies the @runtime_checkable
# service protocols (SheetsService/DriveService/UserInfoService) that beartype enforces
# on the create_*_service() return types; an autospec of the bare Resource class lacks
# the dynamically-added API methods those protocols require.
mock_resource = MagicMock()


class TestAuthState(unittest.TestCase):
    """Test cases for the AuthState enum."""

    def test_auth_state_comparison(self):
        """Test that AuthState comparison operators work correctly."""
        self.assertTrue(AuthState.NO_CLIENT < AuthState.NOT_LOGGED_IN)
        self.assertTrue(AuthState.NOT_LOGGED_IN < AuthState.LOGGED_IN)
        self.assertTrue(AuthState.LOGGED_IN > AuthState.NOT_LOGGED_IN)
        self.assertTrue(AuthState.NOT_LOGGED_IN > AuthState.NO_CLIENT)


class TestAuthInfo(unittest.TestCase):
    """Test cases for the AuthInfo class."""

    def test_auth_info_initialization(self):
        """Test that AuthInfo initializes with the correct state and info."""
        # Test default initialization
        auth_info = AuthInfo()
        self.assertEqual(auth_info.auth_state(), AuthState.NO_CLIENT)
        self.assertIsNone(auth_info.user_email())

        # Test initialization with state and info
        user_info = {"email": "test@example.com"}
        auth_info = AuthInfo(AuthState.LOGGED_IN, user_info)
        self.assertEqual(auth_info.auth_state(), AuthState.LOGGED_IN)
        self.assertEqual(auth_info.user_email(), "test@example.com")


class TestTokenStore(unittest.TestCase):
    """Test cases for the TokenStore class."""

    def setUp(self):
        """Set up test fixtures."""
        self.token_store = TokenStore()
        self.mock_token = json.dumps(
            {"access_token": "test_token", "scopes": ["https://www.googleapis.com/auth/spreadsheets"]}
        )
        self.mock_userinfo = json.dumps({"email": "test@example.com"})

    @patch("keyring.delete_password")
    def test_invalidate(self, mock_delete_password):
        """Test that invalidate clears the current token and removes it from keyring."""
        # Set up the token store with a token
        self.token_store._current_token = self.mock_token
        self.token_store._current_userinfo = self.mock_userinfo

        # Call invalidate
        self.token_store.invalidate()

        # Check that the token and userinfo are cleared
        self.assertIsNone(self.token_store._current_token)
        self.assertIsNone(self.token_store._current_userinfo)

        # Check that delete_password was called twice (once for token, once for userinfo)
        self.assertEqual(mock_delete_password.call_count, 2)

    @patch("keyring.delete_password")
    def test_invalidate_handles_password_delete_error(self, mock_delete_password):
        """Test that invalidate handles PasswordDeleteError gracefully."""
        # Set up the token store with a token
        self.token_store._current_token = self.mock_token
        self.token_store._current_userinfo = self.mock_userinfo

        # Make delete_password raise PasswordDeleteError
        mock_delete_password.side_effect = PasswordDeleteError("No password found")

        # Call invalidate
        self.token_store.invalidate()

        # Check that the token and userinfo are cleared
        self.assertIsNone(self.token_store._current_token)
        self.assertIsNone(self.token_store._current_userinfo)

        # Check that delete_password was called twice (once for token, once for userinfo)
        self.assertEqual(mock_delete_password.call_count, 2)

    @patch("keyring.delete_password")
    def test_invalidate_deletes_both_token_and_userinfo_entries(self, mock_delete_password):
        """invalidate() remains the only path that erases the userinfo entry (#103).

        Guards against a regression where the deletion reserved for invalidate() is either
        dropped from here or leaks back into the token-only update path.
        """
        self.token_store._current_token = self.mock_token
        self.token_store._current_userinfo = self.mock_userinfo

        self.token_store.invalidate()

        deleted_keys = {call.args[0] for call in mock_delete_password.call_args_list}
        self.assertEqual(deleted_keys, {TokenStore.TOKEN_KEY, TokenStore.USERINFO_KEY})
        self.assertIsNone(self.token_store._current_userinfo)

    @patch("keyring.delete_password")
    @patch("keyring.set_password")
    def test_update_token_preserves_userinfo(self, mock_set_password, mock_delete_password):
        """update_token() writes only the token entry and leaves user info untouched (#103)."""
        self.token_store._current_token = "old_token"
        self.token_store._current_userinfo = self.mock_userinfo

        self.token_store.update_token(self.mock_token)

        # The token entry is written...
        self.assertEqual(self.token_store._current_token, self.mock_token)
        mock_set_password.assert_called_once_with(
            TokenStore.TOKEN_KEY, self.token_store._token_user_id, self.mock_token
        )
        # ...and the cached/stored user info survives untouched.
        self.assertEqual(self.token_store._current_userinfo, self.mock_userinfo)
        mock_delete_password.assert_not_called()

    @patch("keyring.set_password")
    def test_store(self, mock_set_password):
        """Test that store saves the token and userinfo to keyring."""
        # Call store with token and userinfo
        self.token_store.store(self.mock_token, self.mock_userinfo)

        # Check that the token and userinfo are set
        self.assertEqual(self.token_store._current_token, self.mock_token)
        self.assertEqual(self.token_store._current_userinfo, self.mock_userinfo)

        # Check that set_password was called twice (once for token, once for userinfo)
        self.assertEqual(mock_set_password.call_count, 2)

    @patch("keyring.set_password")
    @patch("keyring.delete_password")
    def test_store_with_none_userinfo(self, mock_delete_password, mock_set_password):
        """store(token, None) means "this identity has no user info" and clears the entry (#103).

        This contract is retained deliberately: `store()` is the full-identity write used after a
        fresh OAuth flow, where a missing user info lookup must not leave a previous account's
        email cached. Callers that only rotate the access token must use `update_token()` instead.
        """
        # Call store with token but no userinfo
        self.token_store.store(self.mock_token, None)

        # Check that the token is set and userinfo is None
        self.assertEqual(self.token_store._current_token, self.mock_token)
        self.assertIsNone(self.token_store._current_userinfo)

        # Check that set_password was called once (for token)
        mock_set_password.assert_called_once()

        # Check that delete_password was called once, for the userinfo entry only
        mock_delete_password.assert_called_once_with(TokenStore.USERINFO_KEY, self.token_store._token_user_id)

    @patch("keyring.get_password")
    def test_load(self, mock_get_password):
        """Test that load retrieves the token and userinfo from keyring."""
        # Set up the mock to return token and userinfo
        mock_get_password.side_effect = [self.mock_token, self.mock_userinfo]

        # Call load
        token, userinfo = self.token_store.load()

        # Check that the token and userinfo are returned
        self.assertEqual(token, self.mock_token)
        self.assertEqual(userinfo, self.mock_userinfo)

        # Check that get_password was called twice (once for token, once for userinfo)
        self.assertEqual(mock_get_password.call_count, 2)

    @patch("keyring.get_password")
    def test_load_no_token(self, mock_get_password):
        """Test that load raises ValueError when no token is found."""
        # Set up the mock to return None for token
        mock_get_password.return_value = None

        # Call load and check that it raises ValueError
        with self.assertRaises(ValueError):
            self.token_store.load()

    @patch("keyring.get_password")
    def test_get_credentials(self, mock_get_password):
        """Test that get_credentials returns a Credentials object from the stored token."""
        # Set up the mock to return a token with scopes
        token_with_scopes = json.dumps(
            {
                "access_token": "test_token",
                "refresh_token": "test_refresh",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "scopes": SCOPES,  # Use the actual SCOPES from ripper.ripperlib.auth
            }
        )
        mock_get_password.side_effect = [token_with_scopes, None]

        # Call get_credentials
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_info") as mock_from_info:
            mock_from_info.return_value = MagicMock(spec=Credentials)
            creds = self.token_store.get_credentials()
            self.assertIsNotNone(creds)
            self.assertIsInstance(creds, Credentials)

            # Check that from_authorized_user_info was called with the token data
            mock_from_info.assert_called_once()
            args = mock_from_info.call_args[0][0]
            self.assertEqual(args["access_token"], "test_token")

    @patch("keyring.get_password")
    def test_get_credentials_missing_scopes(self, mock_get_password):
        """get_credentials raises the dedicated MissingScopesError when scopes are missing (#50).

        SystemError is a builtin reserved for interpreter-internal failures; the missing-scope
        condition is a domain/value error, so it now raises MissingScopesError. That class
        subclasses ValueError so existing `except ValueError` sites keep catching it.
        """
        # Set up the mock to return a token without scopes
        token_without_scopes = json.dumps(
            {
                "access_token": "test_token",
                "refresh_token": "test_refresh",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
            }
        )
        mock_get_password.side_effect = [token_without_scopes, None]

        # Missing-scopes now raises MissingScopesError, which is a ValueError subclass.
        self.assertTrue(issubclass(MissingScopesError, ValueError))
        with self.assertRaises(MissingScopesError):
            self.token_store.get_credentials()

    @patch("keyring.get_password")
    def test_get_credentials_partial_scopes(self, mock_get_password):
        """A token missing any required scope raises MissingScopesError (#50).

        Exercises the simplified `any(s not in token_json["scopes"] for s in scopes)` check
        against a token that carries only a subset of the required scopes.
        """
        token_partial_scopes = json.dumps(
            {
                "access_token": "test_token",
                "scopes": ["openid"],  # missing spreadsheets / drive / email
            }
        )
        mock_get_password.side_effect = [token_partial_scopes, None]

        with self.assertRaises(MissingScopesError):
            self.token_store.get_credentials()

    @patch("keyring.get_password")
    def test_get_user_info_corrupt_json_returns_none(self, mock_get_password):
        """get_user_info returns None (not raise) when the stored user info is corrupt (#50).

        The narrowed handler still catches the JSON decode failure it is meant to.
        """
        self.token_store._current_userinfo = "{not-valid-json"
        self.assertIsNone(self.token_store.get_user_info())

    @patch("keyring.get_password")
    def test_get_user_info(self, mock_get_password):
        """Test that get_user_info returns the user info from keyring."""
        # Set up the mock to return token and userinfo
        mock_get_password.side_effect = [self.mock_token, self.mock_userinfo]
        self.token_store._current_userinfo = self.mock_userinfo

        # Call get_user_info
        user_info = self.token_store.get_user_info()

        # Check that the user info is returned
        self.assertEqual(user_info["email"], "test@example.com")


class TestAuthManager(unittest.TestCase):
    """Test cases for the AuthManager class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a fresh AuthManager for each test
        with patch.object(AuthManager, "_instance", None):
            with patch.object(AuthManager, "__init__", return_value=None):
                self.auth_manager = AuthManager()
                self.auth_manager._current_auth_info = AuthInfo(AuthState.NO_CLIENT)
                self.auth_manager._initialized = True
                self.auth_manager._credentials = None
                self.auth_manager._token_store = MagicMock(spec=TokenStore)
                # Create a mock for the signal to prevent "Signal source has been deleted" errors
                self.auth_manager.authStateChanged = MagicMock()

    @patch("keyring.get_password")
    def test_has_oauth_client_credentials(self, mock_get_password):
        """Test that has_oauth_client_credentials returns True when credentials are available."""
        # Set up the mock to return credentials
        mock_get_password.return_value = json.dumps({"client_id": "test_id", "client_secret": "test_secret"})

        # Call has_oauth_client_credentials
        result = self.auth_manager.has_oauth_client_credentials()

        # Check that it returns True
        self.assertTrue(result)

        # Check that get_password was called with the correct arguments
        mock_get_password.assert_called_once_with(OAUTH_CLIENT_KEY, OAUTH_CLIENT_USER)

    @patch("keyring.get_password")
    def test_has_oauth_client_credentials_no_credentials(self, mock_get_password):
        """Test that has_oauth_client_credentials returns False when no credentials are available."""
        # Set up the mock to return None
        mock_get_password.return_value = None

        # Call has_oauth_client_credentials
        result = self.auth_manager.has_oauth_client_credentials()

        # Check that it returns False
        self.assertFalse(result)

    @patch("keyring.get_password")
    def test_load_oauth_client_credentials(self, mock_get_password):
        """Test that load_oauth_client_credentials returns the client ID and secret from keyring."""
        # Set up the mock to return credentials
        mock_get_password.return_value = json.dumps({"client_id": "test_id", "client_secret": "test_secret"})

        # Call load_oauth_client_credentials
        client_id, client_secret = self.auth_manager.load_oauth_client_credentials()

        # Check that the correct values are returned
        self.assertEqual(client_id, "test_id")
        self.assertEqual(client_secret, "test_secret")

    @patch("keyring.get_password")
    def test_has_oauth_client_credentials_does_not_mutate_state(self, mock_get_password):
        """A read of whether client creds exist must not flip auth state or emit a signal (#50).

        `has_oauth_client_credentials` (and the underlying `load_oauth_client_credentials`) are
        getters: they previously called `update_state(NOT_LOGGED_IN)` as a side effect, so a mere
        boolean check could emit `authStateChanged` and move the state machine. State transitions
        belong to imperative call sites (store_oauth_client_credentials / check_stored_credentials).
        """
        mock_get_password.return_value = json.dumps({"client_id": "test_id", "client_secret": "test_secret"})
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NO_CLIENT)
        self.auth_manager.authStateChanged = MagicMock()

        result = self.auth_manager.has_oauth_client_credentials()

        self.assertTrue(result)
        # State unchanged and no signal emitted from the read path.
        self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NO_CLIENT)
        self.auth_manager.authStateChanged.emit.assert_not_called()

    @patch("keyring.get_password")
    def test_load_oauth_client_credentials_does_not_mutate_state(self, mock_get_password):
        """load_oauth_client_credentials is a pure read: no state transition, no signal (#50)."""
        mock_get_password.return_value = json.dumps({"client_id": "test_id", "client_secret": "test_secret"})
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NO_CLIENT)
        self.auth_manager.authStateChanged = MagicMock()

        self.auth_manager.load_oauth_client_credentials()

        self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NO_CLIENT)
        self.auth_manager.authStateChanged.emit.assert_not_called()

    @patch("keyring.set_password")
    def test_store_oauth_client_credentials(self, mock_set_password):
        """Test that store_oauth_client_credentials saves the credentials to keyring."""
        # Call store_oauth_client_credentials
        self.auth_manager.store_oauth_client_credentials("test_id", "test_secret")

        # Check that set_password was called with the correct arguments
        mock_set_password.assert_called_once()
        args = mock_set_password.call_args[0]
        self.assertEqual(args[0], OAUTH_CLIENT_KEY)
        self.assertEqual(args[1], OAUTH_CLIENT_USER)
        # The third argument is a JSON string, parse it and check the values
        creds = json.loads(args[2])
        self.assertEqual(creds["client_id"], "test_id")
        self.assertEqual(creds["client_secret"], "test_secret")

    def test_no_plaintext_token_file_persistence(self):
        """Tokens must persist only via the keyring TokenStore, never a plaintext file (#31).

        Guards against reintroducing the removed file-based path (%APPDATA%/token.json), which
        wrote credentials to disk in the clear and resolved to a bogus location on non-Windows
        platforms where APPDATA is unset.
        """
        for attr in ("_save_credentials", "_load_credentials", "_get_token_path"):
            self.assertFalse(
                hasattr(AuthManager, attr),
                f"{attr} reintroduces plaintext token storage (#31); persist via keyring TokenStore instead",
            )

    def test_update_state(self):
        """Test that update_state updates the auth state and emits a signal."""
        # Mock the signal
        self.auth_manager.authStateChanged = MagicMock()

        # Call update_state
        user_info = {"email": "test@example.com"}
        self.auth_manager.update_state(AuthState.LOGGED_IN, user_info)

        # Check that the auth state was updated
        self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.LOGGED_IN)
        self.assertEqual(self.auth_manager._current_auth_info.user_email(), "test@example.com")

        # Check that the signal was emitted
        self.auth_manager.authStateChanged.emit.assert_called_once()

    def test_update_state_no_change(self):
        """Test that update_state does nothing when the state doesn't change."""
        # Set the current state
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NO_CLIENT)

        # Mock the signal
        self.auth_manager.authStateChanged = MagicMock()

        # Call update_state with the same state
        self.auth_manager.update_state(AuthState.NO_CLIENT)

        # Check that the signal was not emitted
        self.auth_manager.authStateChanged.emit.assert_not_called()

    def test_update_state_logged_in_without_user_info_degrades(self):
        """LOGGED_IN without user_info must degrade to NOT_LOGGED_IN, not raise (#50).

        Previously update_state raised ValueError, which made the offline-startup path in
        check_stored_credentials/authorize a reachable crash. The guard now logs a warning and
        falls back to NOT_LOGGED_IN so the app can start logged out.
        """
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NO_CLIENT)
        self.auth_manager.authStateChanged = MagicMock()

        # Must not raise.
        self.auth_manager.update_state(AuthState.LOGGED_IN)

        self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NOT_LOGGED_IN)
        self.assertIsNone(self.auth_manager._current_auth_info.user_email())
        self.auth_manager.authStateChanged.emit.assert_called_once()

    def test_auth_info(self):
        """Test that auth_info returns the current auth info."""
        # Set the current auth info
        self.auth_manager._current_auth_info = AuthInfo(AuthState.LOGGED_IN, {"email": "test@example.com"})

        # Call auth_info
        result = self.auth_manager.auth_info()

        # Check that it returns the correct auth info
        self.assertEqual(result.auth_state(), AuthState.LOGGED_IN)
        self.assertEqual(result.user_email(), "test@example.com")

    def test_retrieve_user_info(self):
        with patch("ripper.ripperlib.auth.build") as mock_build:
            service = MagicMock()
            userinfo = service.userinfo.return_value
            userinfo.get.return_value.execute.return_value = {"email": "test@example.com"}
            mock_build.return_value = service
            cred = DUMMY_CREDS
            result = self.auth_manager.retrieve_user_info(cred)
            self.assertEqual(result["email"], "test@example.com")
            service.userinfo.assert_called_once()
            userinfo.get.assert_called_once()
            userinfo.get.return_value.execute.assert_called_once()

    @patch.object(AuthManager, "create_userinfo_service")
    def test_retrieve_user_info_error(self, mock_create_service):
        service = MagicMock()
        userinfo = service.userinfo.return_value
        userinfo.get.return_value.execute.side_effect = RefreshError("Token expired")
        mock_create_service.return_value = service
        cred = DUMMY_CREDS
        result = self.auth_manager.retrieve_user_info(cred)
        self.assertIsNone(result)

    def test_refresh_token_success(self):
        """Test that refresh_token refreshes an expired token successfully."""
        mock_cred = make_mock_creds(expired=True, valid=True)
        # Call refresh_token
        result = self.auth_manager.refresh_token(mock_cred)
        self.assertEqual(result, mock_cred)
        self.auth_manager._token_store.update_token.assert_called_once_with(mock_cred.to_json())
        # A token-only rotation must never go through store(), whose None-userinfo argument
        # would erase the cached identity (#103).
        self.auth_manager._token_store.store.assert_not_called()

    @patch("keyring.delete_password")
    @patch("keyring.set_password")
    def test_refresh_token_preserves_cached_user_info(self, mock_set_password, mock_delete_password):
        """A successful refresh must not erase the cached email/name from the keyring (#103).

        Storing the refreshed token via `store(token)` (no userinfo argument) deleted the userinfo
        keyring entry on every routine refresh, forcing an extra retrieve_user_info() round-trip at
        startup - and leaving user_info None if that call failed.
        """
        token_store = TokenStore()
        token_store._current_token = json.dumps({"access_token": "old_token"})
        token_store._current_userinfo = json.dumps({"email": "test@example.com"})
        self.auth_manager._token_store = token_store

        mock_cred = make_mock_creds(expired=True, valid=True)
        result = self.auth_manager.refresh_token(mock_cred)

        self.assertEqual(result, mock_cred)
        # The refreshed token was written to the keyring...
        mock_set_password.assert_called_once_with(TokenStore.TOKEN_KEY, token_store._token_user_id, mock_cred.to_json())
        # ...and the cached user info survived, in memory and in the keyring.
        mock_delete_password.assert_not_called()
        self.assertEqual(token_store.get_user_info(), {"email": "test@example.com"})

    def test_refresh_token_failure(self):
        """Test that refresh_token handles refresh failures."""
        mock_cred = make_mock_creds(expired=True, valid=False)
        result = self.auth_manager.refresh_token(mock_cred)
        self.assertIsNone(result)
        self.auth_manager._token_store.invalidate.assert_called_once()

    def test_refresh_token_refresh_error(self):
        """Test that refresh_token handles RefreshError."""
        mock_cred = make_mock_creds(expired=True, valid=True)

        def raise_refresh(*args, **kwargs):
            raise RefreshError("Token expired")

        mock_cred.refresh.side_effect = raise_refresh
        result = self.auth_manager.refresh_token(mock_cred)
        self.assertIsNone(result)
        self.auth_manager._token_store.invalidate.assert_called_once()

    def test_refresh_token_transport_error(self):
        """refresh_token must catch TransportError without invalidating stored credentials (#102).

        TransportError is a sibling of RefreshError under GoogleAuthError, not a subclass, so a
        bare `except RefreshError` lets an offline refresh crash the app. A transport failure is
        transient (offline, DNS, timeout) — the credentials were never rejected, so the keyring
        entries must be preserved for the next launch.
        """
        mock_cred = make_mock_creds(expired=True, valid=True)
        mock_cred.refresh.side_effect = TransportError("connection error: DNS failure")

        result = self.auth_manager.refresh_token(mock_cred)

        self.assertIsNone(result)
        self.auth_manager._token_store.invalidate.assert_not_called()
        self.auth_manager._token_store.store.assert_not_called()

    def test_refresh_token_other_transient_transport_errors(self):
        """google.auth's TimeoutError and ResponseError are also transient — no invalidation (#102)."""
        for transient_exc in (GoogleAuthTimeoutError("request timed out"), ResponseError("bad response read")):
            with self.subTest(exception=type(transient_exc).__name__):
                self.auth_manager._token_store.reset_mock()
                mock_cred = make_mock_creds(expired=True, valid=True)
                mock_cred.refresh.side_effect = transient_exc

                result = self.auth_manager.refresh_token(mock_cred)

                self.assertIsNone(result)
                self.auth_manager._token_store.invalidate.assert_not_called()
                self.auth_manager._token_store.store.assert_not_called()

    def test_refresh_token_retryable_refresh_error_preserves_store(self):
        """A retryable RefreshError (token endpoint 500/503, server_error) must not invalidate (#102).

        google-auth raises RefreshError with retryable=True for retryable HTTP failures after its
        internal retries are exhausted. That is environmental, not a rejected token, so the keyring
        entries must be preserved for the next launch.
        """
        mock_cred = make_mock_creds(expired=True, valid=True)
        mock_cred.refresh.side_effect = RefreshError("server unavailable", retryable=True)

        result = self.auth_manager.refresh_token(mock_cred)

        self.assertIsNone(result)
        self.auth_manager._token_store.invalidate.assert_not_called()
        self.auth_manager._token_store.store.assert_not_called()

    def test_refresh_token_generic_google_auth_error(self):
        """refresh_token must catch any GoogleAuthError subclass, not just RefreshError (#102)."""

        class SomeOtherGoogleAuthError(GoogleAuthError):
            pass

        mock_cred = make_mock_creds(expired=True, valid=True)
        mock_cred.refresh.side_effect = SomeOtherGoogleAuthError("some other auth failure")

        result = self.auth_manager.refresh_token(mock_cred)

        self.assertIsNone(result)
        self.auth_manager._token_store.invalidate.assert_called_once()
        self.auth_manager._token_store.store.assert_not_called()

    def test_attempt_load_stored_token_success(self):
        """Test that attempt_load_stored_token loads a valid token successfully."""
        mock_cred = make_mock_creds(expired=False, valid=True)
        self.auth_manager._token_store.get_credentials.return_value = mock_cred
        result = self.auth_manager.attempt_load_stored_token()
        self.assertEqual(result, mock_cred)

    def test_attempt_load_stored_token_expired(self):
        """Test that attempt_load_stored_token refreshes an expired token."""
        mock_cred = make_mock_creds(expired=True, valid=True)
        self.auth_manager._token_store.get_credentials.return_value = mock_cred
        refreshed_cred = make_mock_creds(expired=False, valid=True)
        with patch.object(self.auth_manager, "refresh_token", return_value=refreshed_cred):
            result = self.auth_manager.attempt_load_stored_token()
            self.assertEqual(result, refreshed_cred)

    def test_attempt_load_stored_token_expired_refresh_transport_error(self):
        """An expired stored token whose refresh fails offline must yield None, not raise (#102).

        The stored token and user info must stay in the keyring: the refresh failed for
        environmental reasons, not because the credentials were rejected, so the next launch
        (with connectivity) must be able to refresh silently instead of forcing a new OAuth flow.
        """
        mock_cred = make_mock_creds(expired=True, valid=True)
        mock_cred.refresh.side_effect = TransportError("network unreachable")
        self.auth_manager._token_store.get_credentials.return_value = mock_cred

        result = self.auth_manager.attempt_load_stored_token()

        self.assertIsNone(result)
        self.auth_manager._token_store.invalidate.assert_not_called()
        self.auth_manager._token_store.store.assert_not_called()

    def test_attempt_load_stored_token_no_token(self):
        """Test that attempt_load_stored_token handles the case when no token is found."""
        # Set up the token store to raise ValueError
        self.auth_manager._token_store.get_credentials.side_effect = ValueError("No token found")

        # Call attempt_load_stored_token
        result = self.auth_manager.attempt_load_stored_token()

        # Check that it returns None
        self.assertIsNone(result)

    def test_attempt_load_stored_token_invalid_token(self):
        """attempt_load_stored_token handles a missing-scopes token by returning None (#50).

        The store now raises MissingScopesError (a ValueError subclass) rather than SystemError.
        """
        # Set up the token store to raise MissingScopesError
        self.auth_manager._token_store.get_credentials.side_effect = MissingScopesError(
            "Required scopes are missing from token."
        )

        # Call attempt_load_stored_token
        result = self.auth_manager.attempt_load_stored_token()

        # Check that it returns None
        self.assertIsNone(result)

    @patch.object(AuthManager, "load_oauth_client_credentials")
    @patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config")
    def test_acquire_new_credentials_success(self, mock_flow, mock_load_creds):
        mock_load_creds.return_value = ("test_id", "test_secret")
        mock_flow_instance = MagicMock()
        mock_flow_instance.run_local_server.return_value = DUMMY_CREDS
        mock_flow.return_value = mock_flow_instance
        result = self.auth_manager.acquire_new_credentials()
        self.assertEqual(result, DUMMY_CREDS)
        mock_flow.assert_called_once()
        client_config = mock_flow.call_args[0][0]
        self.assertEqual(client_config["installed"]["client_id"], "test_id")
        self.assertEqual(client_config["installed"]["client_secret"], "test_secret")

    @patch.object(AuthManager, "load_oauth_client_credentials")
    def test_acquire_new_credentials_no_client_config(self, mock_load_creds):
        """Test that acquire_new_credentials handles the case when no client config is available."""
        mock_load_creds.return_value = (None, None)
        result = self.auth_manager.acquire_new_credentials()
        self.assertIsNone(result)
        self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NO_CLIENT)

    @patch.object(AuthManager, "load_oauth_client_credentials", return_value=("test_id", "test_secret"))
    @patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config")
    def test_acquire_new_credentials_bounds_the_local_server_wait(self, mock_flow, mock_load_creds):
        """run_local_server must be given a timeout so a stalled sign-in can't hang forever (#37)."""
        from ripper.ripperlib.auth import OAUTH_FLOW_TIMEOUT_SECONDS

        mock_flow.return_value.run_local_server.return_value = DUMMY_CREDS

        result = self.auth_manager.acquire_new_credentials()

        self.assertEqual(result, DUMMY_CREDS)
        _, kwargs = mock_flow.return_value.run_local_server.call_args
        self.assertEqual(kwargs.get("timeout_seconds"), OAUTH_FLOW_TIMEOUT_SECONDS)

    @patch.object(AuthManager, "load_oauth_client_credentials", return_value=("test_id", "test_secret"))
    @patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config")
    def test_acquire_new_credentials_flow_failure_is_handled(self, mock_flow, mock_load_creds):
        """A failure/hang in run_local_server must be caught, not propagate into the UI path (#37)."""
        mock_flow.return_value.run_local_server.side_effect = RuntimeError("browser closed / timed out")

        result = self.auth_manager.acquire_new_credentials()

        self.assertIsNone(result)
        # Client is configured, so a login failure leaves us NOT_LOGGED_IN (not NO_CLIENT).
        self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NOT_LOGGED_IN)

    def test_check_stored_credentials_no_client(self):
        """Test that check_stored_credentials handles the case when no client is configured."""
        # Set up the auth manager with NO_CLIENT state
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NO_CLIENT)

        # Set up has_oauth_client_credentials to return False
        with patch.object(self.auth_manager, "has_oauth_client_credentials", return_value=False):
            # Call check_stored_credentials
            self.auth_manager.check_stored_credentials()

            # Check that the auth state is still NO_CLIENT
            self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NO_CLIENT)

    def test_check_stored_credentials_with_valid_token(self):
        """Test that check_stored_credentials loads a valid token and updates the state."""
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NOT_LOGGED_IN)
        with patch.object(self.auth_manager, "has_oauth_client_credentials", return_value=True):
            with patch.object(self.auth_manager, "attempt_load_stored_token", return_value=make_mock_creds()):
                user_info = {"email": "test@example.com"}
                self.auth_manager._token_store.get_user_info.return_value = user_info
                self.auth_manager.check_stored_credentials()
                self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.LOGGED_IN)
                self.assertEqual(self.auth_manager._current_auth_info.user_email(), "test@example.com")

    def test_check_stored_credentials_valid_token_but_no_user_info_degrades(self):
        """Offline startup: a valid token with no obtainable user info must not crash (#50).

        When the cached user info is absent and retrieve_user_info() also fails (e.g. offline),
        check_stored_credentials passes user_info=None into update_state(LOGGED_IN). That used to
        raise ValueError and take down startup; it must instead degrade to NOT_LOGGED_IN.
        """
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NOT_LOGGED_IN)
        self.auth_manager.authStateChanged = MagicMock()
        with patch.object(self.auth_manager, "has_oauth_client_credentials", return_value=True):
            with patch.object(self.auth_manager, "attempt_load_stored_token", return_value=make_mock_creds()):
                # No cached user info, and the live lookup also fails.
                self.auth_manager._token_store.get_user_info.return_value = None
                with patch.object(self.auth_manager, "retrieve_user_info", return_value=None):
                    # Must not raise.
                    self.auth_manager.check_stored_credentials()

        self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NOT_LOGGED_IN)

    def test_check_stored_credentials_with_no_token(self):
        """Test that check_stored_credentials updates the state to NOT_LOGGED_IN when no token is found."""
        # Set up the auth manager with NO_CLIENT state
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NO_CLIENT)

        # Set up has_oauth_client_credentials to return True
        with patch.object(self.auth_manager, "has_oauth_client_credentials", return_value=True):
            # Set up attempt_load_stored_token to return None
            with patch.object(self.auth_manager, "attempt_load_stored_token", return_value=None):
                # Call check_stored_credentials
                self.auth_manager.check_stored_credentials()

                # Check that the auth state was updated to NOT_LOGGED_IN
                self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NOT_LOGGED_IN)

    def test_authorize_with_cached_credentials(self):
        """Test that authorize returns cached credentials if available."""
        self.auth_manager._credentials = make_mock_creds()
        result = self.auth_manager.authorize()
        self.assertEqual(result, self.auth_manager._credentials)

    def test_authorize_force_refresh(self):
        """Test that authorize forces a refresh when force=True."""
        # Set up the auth manager with cached credentials
        self.auth_manager._credentials = make_mock_creds()

        # Create a new credential to return
        new_cred = MagicMock()

        # Create a real authorize method reference to avoid recursion
        original_authorize = self.auth_manager.authorize

        # Create a patched version that returns the new credential
        def patched_authorize(*args, **kwargs):
            # Only patch the first call to avoid recursion
            self.auth_manager.authorize = original_authorize
            return new_cred

        # Replace the authorize method with our patched version
        self.auth_manager.authorize = patched_authorize

        # Call authorize with force=True
        result = self.auth_manager.authorize(force=True)

        # Check that it returns the new credentials
        self.assertEqual(result, new_cred)

        # Restore the original method
        self.auth_manager.authorize = original_authorize

    def test_authorize_no_cached_credentials(self):
        """Test that authorize loads stored credentials when no cached credentials are available."""
        # Set up the auth manager with no cached credentials
        self.auth_manager._credentials = None

        # Create a mock credential to return
        mock_cred = MagicMock()

        # Create a real authorize method reference to avoid recursion
        original_authorize = self.auth_manager.authorize

        # Create a patched version that returns the mock credential
        def patched_authorize(*args, **kwargs):
            # Only patch the first call to avoid recursion
            self.auth_manager.authorize = original_authorize
            return mock_cred

        # Replace the authorize method with our patched version
        self.auth_manager.authorize = patched_authorize

        # Call authorize
        result = self.auth_manager.authorize()

        # Check that it returns the loaded credentials
        self.assertEqual(result, mock_cred)

        # Restore the original method
        self.auth_manager.authorize = original_authorize

    def test_authorize_acquire_new_credentials(self):
        """Test that authorize acquires new credentials when no stored credentials are available."""
        # Set up the auth manager with no cached credentials
        self.auth_manager._credentials = None

        # Create a mock credential to return
        mock_cred = MagicMock()

        # Create a real authorize method reference to avoid recursion
        original_authorize = self.auth_manager.authorize

        # Create a patched version that returns the mock credential
        def patched_authorize(*args, **kwargs):
            # Only patch the first call to avoid recursion
            self.auth_manager.authorize = original_authorize
            return mock_cred

        # Replace the authorize method with our patched version
        self.auth_manager.authorize = patched_authorize

        # Call authorize
        result = self.auth_manager.authorize()

        # Check that it returns the new credentials
        self.assertEqual(result, mock_cred)

        # Restore the original method
        self.auth_manager.authorize = original_authorize

    def test_authorize_failure(self):
        """Test that authorize handles the case when no credentials can be obtained."""
        # Set up the auth manager with no cached credentials
        self.auth_manager._credentials = None

        # Create a real authorize method reference to avoid recursion
        original_authorize = self.auth_manager.authorize

        # Create a patched version that returns None
        def patched_authorize(*args, **kwargs):
            # Only patch the first call to avoid recursion
            self.auth_manager.authorize = original_authorize
            return None

        # Replace the authorize method with our patched version
        self.auth_manager.authorize = patched_authorize

        # Call authorize
        result = self.auth_manager.authorize()

        # Check that it returns None
        self.assertIsNone(result)

        # Restore the original method
        self.auth_manager.authorize = original_authorize

    def test_create_sheets_service(self):
        mock_cred = make_mock_creds()
        with patch.object(self.auth_manager, "authorize", return_value=mock_cred):
            with patch("ripper.ripperlib.auth.build", return_value=mock_resource):
                result = self.auth_manager.create_sheets_service()
                self.assertEqual(result, mock_resource)

    def test_create_drive_service(self):
        mock_cred = make_mock_creds()
        with patch.object(self.auth_manager, "authorize", return_value=mock_cred):
            with patch("ripper.ripperlib.auth.build", return_value=mock_resource):
                result = self.auth_manager.create_drive_service()
                self.assertEqual(result, mock_resource)

    def test_create_userinfo_service(self):
        mock_cred = make_mock_creds()
        with patch("ripper.ripperlib.auth.build", return_value=mock_resource):
            result = self.auth_manager.create_userinfo_service(mock_cred)
            self.assertEqual(result, mock_resource)

    def test_create_userinfo_service_no_cred(self):
        mock_cred = make_mock_creds()
        with patch.object(self.auth_manager, "authorize", return_value=mock_cred):
            with patch("ripper.ripperlib.auth.build", return_value=mock_resource):
                result = self.auth_manager.create_userinfo_service()
                self.assertEqual(result, mock_resource)

    def test_create_userinfo_service_auth_failure(self):
        with patch.object(self.auth_manager, "authorize", return_value=None):
            with patch("ripper.ripperlib.auth.build") as mock_build:
                result = self.auth_manager.create_userinfo_service()
                self.assertIsNone(result)
                mock_build.assert_not_called()

    def test_authorize_without_user_info_does_not_retain_usable_credentials(self):
        """A usable token but no obtainable user info must not present a half-authenticated session (#50).

        Invariant: LOGGED_IN <=> user_info present <=> _credentials usable. When retrieve_user_info
        returns None, authorize() must degrade to NOT_LOGGED_IN AND leave no usable credential behind:
        _credentials stays None and authorize() returns None, so the caller treats this session as
        "not authorized" and retries next time rather than operating under a logged-out state.
        """
        self.auth_manager._credentials = None
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NOT_LOGGED_IN)
        mock_cred = make_mock_creds()
        with patch.object(self.auth_manager, "attempt_load_stored_token", return_value=mock_cred):
            with patch.object(self.auth_manager, "retrieve_user_info", return_value=None):
                result = self.auth_manager.authorize()

        self.assertIsNone(result)
        self.assertIsNone(self.auth_manager._credentials)
        self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NOT_LOGGED_IN)

    def test_services_refuse_when_user_info_unavailable(self):
        """create_*_service must not build authenticated clients when user info is unavailable (#50).

        Because _credentials is only ever set when LOGGED_IN, authorize() returns None on this path,
        so the service creators return None and never call build() - no authenticated client is handed
        out while auth_info says the user is logged out.
        """
        self.auth_manager._credentials = None
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NOT_LOGGED_IN)
        mock_cred = make_mock_creds()
        with patch.object(self.auth_manager, "attempt_load_stored_token", return_value=mock_cred):
            with patch.object(self.auth_manager, "retrieve_user_info", return_value=None):
                with patch("ripper.ripperlib.auth.build") as mock_build:
                    self.assertIsNone(self.auth_manager.create_sheets_service())
                    self.assertIsNone(self.auth_manager.create_drive_service())
                    mock_build.assert_not_called()
        # No usable credential was cached as a side effect of the service calls.
        self.assertIsNone(self.auth_manager._credentials)

    def test_check_stored_credentials_no_user_info_leaves_credentials_unusable_and_token_preserved(self):
        """A valid stored token with no obtainable user info must not cache a usable credential (#50).

        check_stored_credentials previously cached stored_cred into _credentials before the state
        downgrade, so the next authorize() short-circuited and returned it without retrying user-info
        recovery. It must instead leave _credentials unset (so authorize() retries) while preserving
        the stored keyring token (a profile-fetch failure is transient, not a token rejection - #103).
        """
        self.auth_manager._credentials = None
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NOT_LOGGED_IN)
        mock_cred = make_mock_creds()
        with patch.object(self.auth_manager, "has_oauth_client_credentials", return_value=True):
            with patch.object(self.auth_manager, "attempt_load_stored_token", return_value=mock_cred):
                self.auth_manager._token_store.get_user_info.return_value = None
                with patch.object(self.auth_manager, "retrieve_user_info", return_value=None):
                    self.auth_manager.check_stored_credentials()

        # In-memory credential is not cached and the session is logged out...
        self.assertIsNone(self.auth_manager._credentials)
        self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.NOT_LOGGED_IN)
        # ...and the stored keyring token was NOT invalidated (#103 transient-preservation guarantee).
        self.auth_manager._token_store.invalidate.assert_not_called()

        # The NEXT authorize() must actually retry user-info recovery rather than returning a cached
        # usable credential.
        with patch.object(self.auth_manager, "attempt_load_stored_token", return_value=mock_cred) as mock_load:
            with patch.object(self.auth_manager, "retrieve_user_info", return_value=None) as mock_retrieve:
                self.assertIsNone(self.auth_manager.authorize())
                mock_load.assert_called_once()
                mock_retrieve.assert_called_once()

    def test_authorize_happy_path_sets_credentials_and_builds_services(self):
        """Happy path is unchanged: user_info present -> LOGGED_IN, _credentials set, services build (#50)."""
        self.auth_manager._credentials = None
        self.auth_manager._current_auth_info = AuthInfo(AuthState.NOT_LOGGED_IN)
        mock_cred = make_mock_creds()
        user_info = {"email": "test@example.com"}
        with patch.object(self.auth_manager, "attempt_load_stored_token", return_value=mock_cred):
            with patch.object(self.auth_manager, "retrieve_user_info", return_value=user_info):
                result = self.auth_manager.authorize()

                self.assertEqual(result, mock_cred)
                self.assertEqual(self.auth_manager._credentials, mock_cred)
                self.assertEqual(self.auth_manager._current_auth_info.auth_state(), AuthState.LOGGED_IN)
                self.assertEqual(self.auth_manager._current_auth_info.user_email(), "test@example.com")

                with patch("ripper.ripperlib.auth.build", return_value=mock_resource):
                    self.assertEqual(self.auth_manager.create_sheets_service(), mock_resource)
                    self.assertEqual(self.auth_manager.create_drive_service(), mock_resource)
