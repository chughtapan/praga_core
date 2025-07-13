"""Microsoft Graph API authentication using OAuth 2.0."""

import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests
from requests_oauthlib import OAuth2Session

from pragweb.api_clients.base import BaseAuthManager
from pragweb.secrets_manager import get_secrets_manager

logger = logging.getLogger(__name__)

# Thread-local storage to safely cache per-thread Microsoft Graph service objects.
_thread_local = threading.local()

# Microsoft Graph OAuth 2.0 endpoints
AUTHORIZATION_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

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
    "offline_access",  # Required for refresh tokens
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
        self._client_secret: Optional[str] = None
        self._redirect_uri: Optional[str] = None

        self._authenticate()
        self._initialized = True

    def _authenticate(self) -> None:
        """Authenticate with Microsoft Graph API."""
        # Get client credentials from environment variables
        # TODO: Add Microsoft fields to AppConfig for consistency
        import os

        self._client_id = os.getenv("MICROSOFT_CLIENT_ID", "")
        self._client_secret = os.getenv("MICROSOFT_CLIENT_SECRET", "")
        self._redirect_uri = os.getenv(
            "MICROSOFT_REDIRECT_URI", "http://localhost:8080"
        )

        # Try to load existing token
        self._load_token()

        # If no valid token, need to authenticate
        if not self._access_token or self._is_token_expired():
            if self._refresh_token:
                self._refresh_access_token()
            else:
                self._perform_oauth_flow()

    def _load_token(self) -> None:
        """Load existing token from storage."""
        try:
            secrets_manager = get_secrets_manager()
            token_data = secrets_manager.get_oauth_token("microsoft")

            if token_data:
                if isinstance(token_data, str):
                    token_data = json.loads(token_data)

                self._access_token = token_data.get("access_token")
                self._refresh_token = token_data.get("refresh_token")

                if "expires_at" in token_data:
                    self._token_expires_at = datetime.fromtimestamp(
                        token_data["expires_at"]
                    )

                logger.info("Loaded existing Microsoft token")
        except Exception as e:
            logger.warning(f"Failed to load Microsoft token: {e}")

    def _save_token(self) -> None:
        """Save token to storage."""
        try:
            secrets_manager = get_secrets_manager()
            secrets_manager.store_oauth_token(
                service_name="microsoft",
                access_token=self._access_token or "",
                refresh_token=self._refresh_token,
                token_type="Bearer",
                expires_at=self._token_expires_at,
            )
            logger.info("Saved Microsoft token")
        except Exception as e:
            logger.error(f"Failed to save Microsoft token: {e}")

    def _perform_oauth_flow(self) -> None:
        """Perform OAuth 2.0 flow to get access token."""
        # Create OAuth2 session
        oauth = OAuth2Session(
            client_id=self._client_id,
            redirect_uri=self._redirect_uri,
            scope=_SCOPES,
        )

        # Get authorization URL
        authorization_url, state = oauth.authorization_url(
            AUTHORIZATION_URL,
            prompt="consent",  # Force consent screen
        )

        logger.info(
            f"Please visit this URL to authorize the application: {authorization_url}"
        )
        print(
            f"\nPlease visit this URL to authorize the application:\n{authorization_url}\n"
        )

        # Get authorization code from user
        authorization_response = input("Enter the full callback URL: ").strip()

        # Exchange authorization code for access token
        token = oauth.fetch_token(
            TOKEN_URL,
            authorization_response=authorization_response,
            client_secret=self._client_secret,
        )

        self._access_token = token["access_token"]
        self._refresh_token = token.get("refresh_token")

        # Calculate expiration time
        expires_in = token.get("expires_in", 3600)
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

        self._save_token()
        logger.info("Successfully obtained Microsoft access token")

    def _refresh_access_token(self) -> None:
        """Refresh the access token using refresh token."""
        if not self._refresh_token:
            logger.error("No refresh token available")
            return

        try:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }

            response = requests.post(TOKEN_URL, data=data)
            response.raise_for_status()

            token_data = response.json()

            self._access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                self._refresh_token = token_data["refresh_token"]

            # Calculate expiration time
            expires_in = token_data.get("expires_in", 3600)
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)

            self._save_token()
            logger.info("Successfully refreshed Microsoft access token")

        except Exception as e:
            logger.error(f"Failed to refresh access token: {e}")
            # If refresh fails, need to re-authenticate
            self._perform_oauth_flow()

    def _is_token_expired(self) -> bool:
        """Check if the access token is expired."""
        if not self._token_expires_at:
            return True

        # Consider token expired if it expires within 5 minutes
        return datetime.now() >= (self._token_expires_at - timedelta(minutes=5))

    async def get_credentials(self) -> Dict[str, Any]:
        """Get authentication credentials."""
        if not self._access_token or self._is_token_expired():
            if self._refresh_token:
                self._refresh_access_token()
            else:
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
            if self._refresh_token:
                self._refresh_access_token()
            else:
                raise Exception("Authentication required")


# Global instance
_auth_manager_instance: Optional[MicrosoftAuthManager] = None


def get_microsoft_auth_manager() -> MicrosoftAuthManager:
    """Get the global Microsoft auth manager instance."""
    global _auth_manager_instance
    if _auth_manager_instance is None:
        _auth_manager_instance = MicrosoftAuthManager()
    return _auth_manager_instance
