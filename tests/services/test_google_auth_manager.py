"""Tests for GoogleAuthManager scope validation."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

from pragweb.api_clients.google.auth import _SCOPES, GoogleAuthManager
from pragweb.secrets_manager import SecretsManager


class TestGoogleAuthManagerScopeValidation:
    """Tests for GoogleAuthManager scope validation functionality."""

    def setup_method(self):
        """Setup before each test."""
        # Reset singleton instance
        GoogleAuthManager._instance = None
        GoogleAuthManager._initialized = False

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    def test_scopes_match_exact(self, mock_get_secrets, mock_get_config):
        """Test _scopes_match with exact scope match."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        mock_secrets.get_oauth_token.return_value = None
        mock_get_secrets.return_value = mock_secrets

        with patch.object(GoogleAuthManager, "_authenticate"):
            auth_manager = GoogleAuthManager()

        # Test exact match
        assert auth_manager._scopes_match(_SCOPES, _SCOPES) is True

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    def test_scopes_match_superset(self, mock_get_secrets, mock_get_config):
        """Test _scopes_match with stored scopes being a superset."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        mock_secrets.get_oauth_token.return_value = None
        mock_get_secrets.return_value = mock_secrets

        with patch.object(GoogleAuthManager, "_authenticate"):
            auth_manager = GoogleAuthManager()

        # Test superset (stored has more scopes than required)
        stored_scopes = _SCOPES + ["https://www.googleapis.com/auth/extra.scope"]
        assert auth_manager._scopes_match(stored_scopes, _SCOPES) is True

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    def test_scopes_match_subset(self, mock_get_secrets, mock_get_config):
        """Test _scopes_match with stored scopes being a subset."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        mock_secrets.get_oauth_token.return_value = None
        mock_get_secrets.return_value = mock_secrets

        with patch.object(GoogleAuthManager, "_authenticate"):
            auth_manager = GoogleAuthManager()

        # Test subset (stored has fewer scopes than required)
        stored_scopes = _SCOPES[:3]  # Only first 3 scopes
        assert auth_manager._scopes_match(stored_scopes, _SCOPES) is False

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    def test_scopes_match_different(self, mock_get_secrets, mock_get_config):
        """Test _scopes_match with completely different scopes."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        mock_secrets.get_oauth_token.return_value = None
        mock_get_secrets.return_value = mock_secrets

        with patch.object(GoogleAuthManager, "_authenticate"):
            auth_manager = GoogleAuthManager()

        # Test completely different scopes
        stored_scopes = ["https://www.googleapis.com/auth/different.scope"]
        assert auth_manager._scopes_match(stored_scopes, _SCOPES) is False

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    def test_load_credentials_with_matching_scopes(
        self, mock_get_secrets, mock_get_config
    ):
        """Test _load_credentials returns credentials when scopes match."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        # Mock token data with matching scopes
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": datetime.now(timezone.utc),
            "scopes": _SCOPES,
            "extra_data": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        with patch.object(GoogleAuthManager, "_authenticate"):
            auth_manager = GoogleAuthManager()

        credentials = auth_manager._load_credentials(mock_secrets)

        assert credentials is not None
        assert credentials.token == "test_access_token"
        assert credentials.refresh_token == "test_refresh_token"
        assert credentials.scopes == _SCOPES

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    def test_load_credentials_with_mismatched_scopes(
        self, mock_get_secrets, mock_get_config
    ):
        """Test _load_credentials returns None when scopes don't match."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        # Mock token data with insufficient scopes
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": datetime.now(timezone.utc),
            "scopes": _SCOPES[:3],  # Only first 3 scopes
            "extra_data": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        with patch.object(GoogleAuthManager, "_authenticate"):
            auth_manager = GoogleAuthManager()

        credentials = auth_manager._load_credentials(mock_secrets)

        assert credentials is None

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    def test_load_credentials_with_extra_scopes(
        self, mock_get_secrets, mock_get_config
    ):
        """Test _load_credentials returns credentials when stored scopes include extra ones."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        # Mock token data with extra scopes
        extra_scopes = _SCOPES + ["https://www.googleapis.com/auth/extra.scope"]
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": datetime.now(timezone.utc),
            "scopes": extra_scopes,
            "extra_data": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        with patch.object(GoogleAuthManager, "_authenticate"):
            auth_manager = GoogleAuthManager()

        credentials = auth_manager._load_credentials(mock_secrets)

        assert credentials is not None
        assert credentials.token == "test_access_token"
        assert credentials.refresh_token == "test_refresh_token"
        assert credentials.scopes == extra_scopes

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    def test_load_credentials_no_scopes_in_token_data(
        self, mock_get_secrets, mock_get_config
    ):
        """Test _load_credentials handles missing scopes in token data."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        # Mock token data without scopes field
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": datetime.now(timezone.utc),
            "extra_data": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        with patch.object(GoogleAuthManager, "_authenticate"):
            auth_manager = GoogleAuthManager()

        credentials = auth_manager._load_credentials(mock_secrets)

        # Should return credentials since missing scopes defaults to _SCOPES
        assert credentials is not None
        assert credentials.token == "test_access_token"
        assert credentials.refresh_token == "test_refresh_token"
        assert credentials.scopes == _SCOPES

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    @patch("pragweb.api_clients.google.auth.logger")
    def test_load_credentials_logs_scope_mismatch(
        self, mock_logger, mock_get_secrets, mock_get_config
    ):
        """Test _load_credentials logs when scopes don't match."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock(spec=SecretsManager)
        # Mock token data with insufficient scopes
        insufficient_scopes = _SCOPES[:2]  # Only first 2 scopes
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_at": datetime.now(timezone.utc),
            "scopes": insufficient_scopes,
            "extra_data": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        with patch.object(GoogleAuthManager, "_authenticate"):
            auth_manager = GoogleAuthManager()

        credentials = auth_manager._load_credentials(mock_secrets)

        assert credentials is None
        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]
        assert "don't match required scopes" in log_message
        assert "Forcing reauth" in log_message


class TestGoogleAuthManagerIntegration:
    """Integration tests for GoogleAuthManager with scope validation."""

    def setup_method(self):
        """Setup before each test."""
        # Reset singleton instance
        GoogleAuthManager._instance = None
        GoogleAuthManager._initialized = False

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    @patch("pragweb.api_clients.google.auth.InstalledAppFlow")
    def test_auth_manager_forces_reauth_on_scope_mismatch(
        self, mock_flow_class, mock_get_secrets, mock_get_config
    ):
        """Test that auth manager forces reauth when scopes don't match."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock()
        # Mock token data with insufficient scopes (only first 2 scopes)
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "scopes": _SCOPES[:2],  # Insufficient scopes
            "extra_data": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        # Mock the OAuth flow
        mock_flow = Mock()
        mock_new_creds = Mock()
        mock_new_creds.token = "new_access_token"
        mock_new_creds.refresh_token = "new_refresh_token"
        mock_new_creds.scopes = _SCOPES
        mock_flow.run_local_server.return_value = mock_new_creds
        mock_flow_class.from_client_secrets_file.return_value = mock_flow

        # Create auth manager - should trigger reauth due to scope mismatch
        GoogleAuthManager()

        # Verify that new OAuth flow was initiated
        mock_flow_class.from_client_secrets_file.assert_called_once_with(
            "test_creds.json", _SCOPES
        )
        mock_flow.run_local_server.assert_called_once_with(port=0)
        mock_secrets.store_oauth_token.assert_called_once()

    @patch("pragweb.api_clients.google.auth.get_current_config")
    @patch("pragweb.api_clients.google.auth.get_secrets_manager")
    def test_auth_manager_uses_existing_creds_when_scopes_match(
        self, mock_get_secrets, mock_get_config
    ):
        """Test that auth manager uses existing credentials when scopes match."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock()
        # Mock token data with matching scopes
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "scopes": _SCOPES,  # All required scopes
            "extra_data": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        # Mock the credentials to appear valid
        with patch("pragweb.api_clients.google.auth.Credentials") as mock_creds_class:
            mock_creds = Mock()
            mock_creds.valid = True
            mock_creds_class.return_value = mock_creds

            # Create auth manager - should use existing credentials
            GoogleAuthManager()

            # Verify credentials were loaded but no new OAuth flow was initiated
            mock_secrets.get_oauth_token.assert_called_once_with("google")
            # store_oauth_token should not be called since we're using existing creds
            mock_secrets.store_oauth_token.assert_not_called()
