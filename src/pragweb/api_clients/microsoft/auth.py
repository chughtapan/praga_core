"""Microsoft Graph API authentication using MSAL."""

import json
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import msal  # type: ignore[import-untyped]

from pragweb.api_clients.base import BaseAuthManager
from pragweb.config import get_current_config
from pragweb.secrets_manager import get_secrets_manager

logger = logging.getLogger(__name__)

# Thread-local storage to safely cache per-thread Microsoft Graph service objects.
_thread_local = threading.local()

# Microsoft Graph API scopes
_SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Calendars.Read",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/Contacts.Read",
    "https://graph.microsoft.com/Contacts.ReadWrite",
    "https://graph.microsoft.com/Files.Read",
    "https://graph.microsoft.com/Files.ReadWrite",
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Directory.Read.All",
    # Note: offline_access is automatically included by MSAL for refresh tokens
]


class MicrosoftAuthManager(BaseAuthManager):
    """Microsoft Graph API authentication manager."""

    _instance: Optional["MicrosoftAuthManager"] = None
    _initialized = False

    def __new__(cls) -> "MicrosoftAuthManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._client_id: Optional[str] = None
        self._msal_app: Optional[msal.PublicClientApplication] = None

        self._authenticate()
        self._initialized = True

    def _authenticate(self) -> None:
        """Authenticate with Microsoft Graph API using MSAL."""
        # Get client credentials from environment variables
        self._client_id = os.getenv("MICROSOFT_CLIENT_ID", "")

        if not self._client_id:
            raise ValueError("MICROSOFT_CLIENT_ID environment variable is required")

        # Create MSAL app instance
        self._msal_app = msal.PublicClientApplication(
            client_id=self._client_id,
            authority="https://login.microsoftonline.com/common",
        )

        # Try to load existing token
        self._load_token()

        # If no valid token, need to authenticate
        if not self._access_token or self._is_token_expired():
            self._perform_interactive_flow()

    def _load_token(self) -> None:
        """Load existing token from storage."""
        try:
            config = get_current_config()
            secrets_manager = get_secrets_manager(config.secrets_database_url)
            token_data = secrets_manager.get_oauth_token("microsoft")

            if token_data:
                if isinstance(token_data, str):
                    token_data = json.loads(token_data)

                self._access_token = token_data.get("access_token")
                self._refresh_token = token_data.get("refresh_token")

                if "expires_at" in token_data and token_data["expires_at"]:
                    expires_at = token_data["expires_at"]
                    # Handle both datetime objects and timestamps
                    if isinstance(expires_at, datetime):
                        self._token_expires_at = expires_at
                    elif isinstance(expires_at, (int, float)):
                        self._token_expires_at = datetime.fromtimestamp(expires_at)
                    else:
                        # If it's a string, try to parse it
                        self._token_expires_at = datetime.fromisoformat(
                            str(expires_at).replace("Z", "+00:00")
                        )

                logger.info("Loaded existing Microsoft token")
        except Exception as e:
            logger.warning(f"Failed to load Microsoft token: {e}")

    def _save_token(self) -> None:
        """Save token to storage."""
        try:
            config = get_current_config()
            secrets_manager = get_secrets_manager(config.secrets_database_url)

            # Prepare extra data with client information
            extra_data = {}
            if self._client_id:
                extra_data["client_id"] = self._client_id

            secrets_manager.store_oauth_token(
                service_name="microsoft",
                access_token=self._access_token or "",
                refresh_token=self._refresh_token,
                token_type="Bearer",
                expires_at=self._token_expires_at,
                scopes=_SCOPES,
                extra_data=extra_data if extra_data else None,
            )
            logger.info("Saved Microsoft token")
        except Exception as e:
            logger.error(f"Failed to save Microsoft token: {e}")

    def _perform_interactive_flow(self) -> None:
        """Perform interactive OAuth flow using MSAL."""
        if not self._msal_app:
            raise Exception("MSAL app not initialized")

        # Try silent acquisition first (check cache)
        accounts = self._msal_app.get_accounts()
        if accounts:
            logger.info("Found cached account, attempting silent token acquisition")
            result = self._msal_app.acquire_token_silent(
                scopes=_SCOPES, account=accounts[0]
            )
            if result and "access_token" in result:
                self._update_tokens_from_result(result)
                logger.info("Successfully acquired token silently from cache")
                return

        # If silent acquisition failed, perform interactive flow
        logger.info("Starting interactive authentication flow...")
        print("\nA browser window will open for Microsoft authentication.")
        print("Please sign in and authorize the application.")

        result = self._msal_app.acquire_token_interactive(scopes=_SCOPES)

        if "access_token" in result:
            self._update_tokens_from_result(result)
            self._save_token()
            logger.info("Successfully obtained Microsoft access token")
        else:
            error = result.get("error", "Unknown error")
            error_description = result.get("error_description", "No description")
            raise Exception(f"Authentication failed: {error} - {error_description}")

    def _update_tokens_from_result(self, result: Dict[str, Any]) -> None:
        """Update internal token state from MSAL result."""
        self._access_token = result["access_token"]
        self._refresh_token = result.get("refresh_token")

        # Calculate expiration time
        expires_in = result.get("expires_in", 3600)
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

    def _refresh_access_token(self) -> None:
        """Refresh the access token using MSAL silent acquisition."""
        if not self._msal_app:
            logger.error("MSAL app not initialized")
            self._perform_interactive_flow()
            return

        try:
            # Try silent acquisition with cached account
            accounts = self._msal_app.get_accounts()
            if accounts:
                result = self._msal_app.acquire_token_silent(
                    scopes=_SCOPES, account=accounts[0]
                )

                if result and "access_token" in result:
                    self._update_tokens_from_result(result)
                    self._save_token()
                    logger.info("Successfully refreshed Microsoft access token")
                    return

            # If silent refresh fails, fall back to interactive flow
            logger.warning(
                "Silent token refresh failed, falling back to interactive flow"
            )
            self._perform_interactive_flow()

        except Exception as e:
            logger.error(f"Failed to refresh access token: {e}")
            # If refresh fails, need to re-authenticate
            self._perform_interactive_flow()

    def _is_token_expired(self) -> bool:
        """Check if the access token is expired."""
        if not self._token_expires_at:
            return True

        # Consider token expired if it expires within 5 minutes
        return datetime.now() >= (self._token_expires_at - timedelta(minutes=5))

    async def get_credentials(self) -> Dict[str, Any]:
        """Get authentication credentials."""
        if not self._access_token or self._is_token_expired():
            self._refresh_access_token()

        if not self._access_token:
            raise Exception("No valid access token available")

        return {
            "access_token": self._access_token,
            "token_type": "Bearer",
        }

    async def refresh_credentials(self) -> Dict[str, Any]:
        """Refresh authentication credentials."""
        self._refresh_access_token()
        return await self.get_credentials()

    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self._access_token is not None and not self._is_token_expired()

    def get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        if not self.is_authenticated():
            raise Exception("Not authenticated")

        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    def ensure_authenticated(self) -> None:
        """Ensure the user is authenticated, refresh if necessary."""
        if not self.is_authenticated():
            self._refresh_access_token()


# Global instance
_auth_manager_instance: Optional[MicrosoftAuthManager] = None


def get_microsoft_auth_manager() -> MicrosoftAuthManager:
    """Get the global Microsoft auth manager instance."""
    global _auth_manager_instance
    if _auth_manager_instance is None:
        _auth_manager_instance = MicrosoftAuthManager()
    return _auth_manager_instance
