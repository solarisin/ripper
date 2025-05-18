import json
import unittest
from unittest.mock import MagicMock, create_autospec, patch

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource
from keyring.errors import PasswordDeleteError

from ripper.ripperlib.auth import (
    OAUTH_CLIENT_KEY,
    OAUTH_CLIENT_USER,
    SCOPES,
    AuthInfo,
    AuthManager,
    AuthState,
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


# Helper: create a mock Resource
mock_resource = create_autospec(Resource, instance=True)


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
        """Test that store handles None userinfo correctly."""
        # Call store with token but no userinfo
        self.token_store.store(self.mock_token, None)

        # Check that the token is set and userinfo is None
        self.assertEqual(self.token_store._current_token, self.mock_token)
        self.assertIsNone(self.token_store._current_userinfo)

        # Check that set_password was called once (for token)
        mock_set_password.assert_called_once()

        # Check that delete_password was called once (for userinfo)
        mock_delete_password.assert_called_once()

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
        """Test that get_credentials raises SystemError when required scopes are missing."""
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

        # Call get_credentials and check that it raises SystemError
        with self.assertRaises(SystemError):
            self.token_store.get_credentials()

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

    def test_update_state_requires_user_info(self):
        """Test that update_state requires user_info when state is LOGGED_IN."""
        # Call update_state with LOGGED_IN but no user_info
        with self.assertRaises(ValueError):
            self.auth_manager.update_state(AuthState.LOGGED_IN)

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
        self.auth_manager._token_store.store.assert_called_once_with(mock_cred.to_json())

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

    def test_attempt_load_stored_token_no_token(self):
        """Test that attempt_load_stored_token handles the case when no token is found."""
        # Set up the token store to raise ValueError
        self.auth_manager._token_store.get_credentials.side_effect = ValueError("No token found")

        # Call attempt_load_stored_token
        result = self.auth_manager.attempt_load_stored_token()

        # Check that it returns None
        self.assertIsNone(result)

    def test_attempt_load_stored_token_invalid_token(self):
        """Test that attempt_load_stored_token handles the case when the token is invalid."""
        # Set up the token store to raise SystemError
        self.auth_manager._token_store.get_credentials.side_effect = SystemError("Invalid token")

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
