"""Tests for MicrosoftAuthManager token storage functionality."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

from pragweb.api_clients.microsoft.auth import _SCOPES, MicrosoftAuthManager
from pragweb.secrets_manager import SecretsManager


class TestMicrosoftAuthManagerTokenStorage:
    """Tests for MicrosoftAuthManager token storage functionality."""

    def setup_method(self):
        """Setup before each test."""
        # Reset singleton instance
        MicrosoftAuthManager._instance = None
        MicrosoftAuthManager._initialized = False

    @patch("pragweb.api_clients.microsoft.auth.get_current_config")
    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_save_token_includes_scopes_and_extra_data(
        self, mock_get_secrets, mock_get_config
    ):
        """Test _save_token includes scopes and extra_data with client_id."""
        mock_config = Mock()
        mock_config.secrets_database_url = "sqlite:///:memory:"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        mock_get_secrets.return_value = mock_secrets

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()
            auth_manager._access_token = "test_access_token"
            auth_manager._refresh_token = "test_refresh_token"
            auth_manager._token_expires_at = datetime.now(timezone.utc)
            auth_manager._client_id = "test_client_id"

            auth_manager._save_token()

            # Verify store_oauth_token was called with correct parameters
            mock_secrets.store_oauth_token.assert_called_once_with(
                service_name="microsoft",
                access_token="test_access_token",
                refresh_token="test_refresh_token",
                token_type="Bearer",
                expires_at=auth_manager._token_expires_at,
                scopes=_SCOPES,
                extra_data={"client_id": "test_client_id"},
            )

    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_save_token_handles_missing_client_id(self, mock_get_secrets):
        """Test _save_token handles missing client_id gracefully."""
        mock_secrets = Mock(spec=SecretsManager)
        mock_get_secrets.return_value = mock_secrets

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()
            auth_manager._access_token = "test_access_token"
            auth_manager._refresh_token = "test_refresh_token"
            auth_manager._token_expires_at = datetime.now(timezone.utc)
            auth_manager._client_id = None

            auth_manager._save_token()

            # Verify store_oauth_token was called with None extra_data
            mock_secrets.store_oauth_token.assert_called_once_with(
                service_name="microsoft",
                access_token="test_access_token",
                refresh_token="test_refresh_token",
                token_type="Bearer",
                expires_at=auth_manager._token_expires_at,
                scopes=_SCOPES,
                extra_data=None,
            )

    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_save_token_handles_empty_access_token(self, mock_get_secrets):
        """Test _save_token handles empty access token."""
        mock_secrets = Mock(spec=SecretsManager)
        mock_get_secrets.return_value = mock_secrets

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()
            auth_manager._access_token = None
            auth_manager._refresh_token = "test_refresh_token"
            auth_manager._token_expires_at = datetime.now(timezone.utc)
            auth_manager._client_id = "test_client_id"

            auth_manager._save_token()

            # Verify store_oauth_token was called with empty string for access_token
            mock_secrets.store_oauth_token.assert_called_once_with(
                service_name="microsoft",
                access_token="",
                refresh_token="test_refresh_token",
                token_type="Bearer",
                expires_at=auth_manager._token_expires_at,
                scopes=_SCOPES,
                extra_data={"client_id": "test_client_id"},
            )

    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_load_token_with_matching_scopes(self, mock_get_secrets):
        """Test _load_token loads credentials when scopes match."""
        mock_secrets = Mock(spec=SecretsManager)
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": datetime.now(
                timezone.utc
            ),  # Use datetime object like secrets manager returns
            "scopes": _SCOPES,
            "extra_data": {"client_id": "test_client_id"},
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()

            auth_manager._load_token()

            assert auth_manager._access_token == "test_access_token"
            assert auth_manager._refresh_token == "test_refresh_token"
            assert auth_manager._token_expires_at is not None

    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_load_token_handles_json_string_token_data(self, mock_get_secrets):
        """Test _load_token handles JSON string token data."""
        import json

        mock_secrets = Mock(spec=SecretsManager)
        token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": datetime.now(timezone.utc).timestamp(),
        }
        mock_secrets.get_oauth_token.return_value = json.dumps(token_data)
        mock_get_secrets.return_value = mock_secrets

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()

            auth_manager._load_token()

            assert auth_manager._access_token == "test_access_token"
            assert auth_manager._refresh_token == "test_refresh_token"

    @patch("pragweb.api_clients.microsoft.auth.get_current_config")
    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_load_token_handles_datetime_formats(
        self, mock_get_secrets, mock_get_config
    ):
        """Test _load_token handles different datetime formats correctly."""
        mock_config = Mock()
        mock_config.secrets_database_url = "sqlite:///:memory:"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)

        # Test with datetime object (what secrets manager actually returns)
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": datetime.now(timezone.utc),
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()
            auth_manager._load_token()

            assert auth_manager._access_token == "test_access_token"
            assert auth_manager._token_expires_at is not None
            assert isinstance(auth_manager._token_expires_at, datetime)

    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_load_token_handles_timestamp_format(self, mock_get_secrets):
        """Test _load_token handles timestamp format correctly."""
        mock_secrets = Mock(spec=SecretsManager)

        # Test with timestamp (for backward compatibility)
        test_timestamp = datetime.now(timezone.utc).timestamp()
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": test_timestamp,
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()
            auth_manager._load_token()

            assert auth_manager._access_token == "test_access_token"
            assert auth_manager._token_expires_at is not None
            assert isinstance(auth_manager._token_expires_at, datetime)

    @patch("pragweb.api_clients.microsoft.auth.get_current_config")
    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch("pragweb.api_clients.microsoft.auth.logger")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_save_token_logs_errors(
        self, mock_logger, mock_get_secrets, mock_get_config
    ):
        """Test _save_token logs errors when storage fails."""
        mock_config = Mock()
        mock_config.secrets_database_url = "sqlite:///:memory:"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        mock_secrets.store_oauth_token.side_effect = Exception("Storage failed")
        mock_get_secrets.return_value = mock_secrets

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()
            auth_manager._access_token = "test_access_token"
            auth_manager._client_id = "test_client_id"

            auth_manager._save_token()

            mock_logger.error.assert_called_once()
            error_message = mock_logger.error.call_args[0][0]
            assert "Failed to save Microsoft token" in error_message


class TestMicrosoftAuthManagerIntegration:
    """Integration tests for MicrosoftAuthManager with token storage."""

    def setup_method(self):
        """Setup before each test."""
        # Reset singleton instance
        MicrosoftAuthManager._instance = None
        MicrosoftAuthManager._initialized = False

    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch("pragweb.api_clients.microsoft.auth.msal.PublicClientApplication")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_interactive_flow_saves_token_with_scopes(
        self, mock_msal_app, mock_get_secrets
    ):
        """Test that interactive flow saves token with scopes and extra_data."""
        mock_secrets = Mock(spec=SecretsManager)
        mock_secrets.get_oauth_token.return_value = None
        mock_get_secrets.return_value = mock_secrets

        # Mock MSAL app
        mock_app = Mock()
        mock_app.get_accounts.return_value = []
        mock_app.acquire_token_interactive.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
        }
        mock_msal_app.return_value = mock_app

        # Create auth manager - should trigger interactive flow
        MicrosoftAuthManager()

        # Verify token was saved with scopes and extra_data
        mock_secrets.store_oauth_token.assert_called_once()
        call_args = mock_secrets.store_oauth_token.call_args
        assert call_args[1]["scopes"] == _SCOPES
        assert call_args[1]["extra_data"] == {"client_id": "test_client_id"}

    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch("pragweb.api_clients.microsoft.auth.msal.PublicClientApplication")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_refresh_access_token_saves_updated_token(
        self, mock_msal_app, mock_get_secrets
    ):
        """Test that token refresh saves updated token with scopes."""
        mock_secrets = Mock(spec=SecretsManager)
        mock_secrets.get_oauth_token.return_value = None
        mock_get_secrets.return_value = mock_secrets

        # Mock MSAL app for refresh
        mock_app = Mock()
        mock_account = {"account_id": "test_account"}
        mock_app.get_accounts.return_value = [mock_account]
        mock_app.acquire_token_silent.return_value = {
            "access_token": "refreshed_access_token",
            "refresh_token": "refreshed_refresh_token",
            "expires_in": 3600,
        }
        mock_msal_app.return_value = mock_app

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()
            auth_manager._msal_app = mock_app

            auth_manager._refresh_access_token()

            # Verify refreshed token was saved with scopes and extra_data
            assert mock_secrets.store_oauth_token.call_count >= 1
            # Check the last call (from refresh)
            last_call_args = mock_secrets.store_oauth_token.call_args
            assert last_call_args[1]["access_token"] == "refreshed_access_token"
            assert last_call_args[1]["scopes"] == _SCOPES
