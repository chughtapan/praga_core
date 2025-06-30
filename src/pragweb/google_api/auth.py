"""Google API authentication using singleton pattern."""

import logging
from datetime import timezone
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from googleapiclient.discovery import build  # type: ignore[import-untyped]

from pragweb.config import get_current_config
from pragweb.secrets_manager import SecretsManager, get_secrets_manager

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


class GoogleAuthManager:
    """Singleton Google API authentication manager."""

    _instance: Optional["GoogleAuthManager"] = None
    _initialized = False

    def __new__(cls) -> "GoogleAuthManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._creds: Optional[Credentials] = None
        self._gmail_service = None
        self._calendar_service = None
        self._docs_service = None
        self._drive_service = None
        self._authenticate()
        self._initialized = True

    def _get_credentials_path(self) -> str:
        """Get path to credentials file."""
        return get_current_config().google_credentials_file

    def _load_credentials(
        self, secrets_manager: SecretsManager
    ) -> Optional[Credentials]:
        token_data = secrets_manager.get_oauth_token("google")
        if not token_data:
            logger.debug("No existing token data found for Google")
            return None

        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]
        expires_at = token_data.get("expires_at")
        scopes = token_data.get("scopes", _SCOPES)

        # Get client info from extra_data or use None for missing fields
        extra_data = token_data.get("extra_data", {})
        client_id = extra_data.get("client_id")
        client_secret = extra_data.get("client_secret")
        token_uri = extra_data.get("token_uri", "https://oauth2.googleapis.com/token")

        # Create credentials object
        creds = Credentials(  # type: ignore[no-untyped-call]
            token=access_token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes,
        )

        # Set expiry if available
        if expires_at:
            creds.expiry = expires_at

        return creds

    def _store_credentials(
        self, creds: Credentials, secrets_manager: SecretsManager
    ) -> None:
        """Save Google credentials to secrets manager."""
        # Convert expiry to datetime if it exists
        expires_at = None
        if hasattr(creds, "expiry") and creds.expiry:
            expires_at = creds.expiry
            # Ensure timezone-aware datetime
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

        # Prepare extra data with OAuth client information
        extra_data = {}
        if hasattr(creds, "client_id") and creds.client_id:
            extra_data["client_id"] = creds.client_id
        if hasattr(creds, "client_secret") and creds.client_secret:
            extra_data["client_secret"] = creds.client_secret
        if hasattr(creds, "token_uri") and creds.token_uri:
            extra_data["token_uri"] = creds.token_uri

        # Store in secrets manager
        assert creds.token is not None
        secrets_manager.store_oauth_token(
            service_name="google",
            access_token=creds.token,
            refresh_token=creds.refresh_token,
            token_type="Bearer",
            expires_at=expires_at,
            scopes=(
                list(creds.scopes)
                if hasattr(creds, "scopes") and creds.scopes
                else _SCOPES
            ),
            extra_data=extra_data if extra_data else None,
        )

    def _authenticate(self) -> None:
        """Authenticate with Google APIs."""
        config = get_current_config()
        secrets_manager = get_secrets_manager(config.secrets_database_url)

        self._creds = self._load_credentials(secrets_manager)
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())  # type: ignore[no-untyped-call]
                self._store_credentials(self._creds, secrets_manager)
            else:
                credentials_path = self._get_credentials_path()
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, _SCOPES
                )
                self._creds = flow.run_local_server(port=0)
                # Save new credentials
                self._store_credentials(self._creds, secrets_manager)

    def get_gmail_service(self) -> Any:
        """Get Gmail service (cached)."""
        if self._gmail_service is None:
            self._gmail_service = build("gmail", "v1", credentials=self._creds)
        return self._gmail_service

    def get_calendar_service(self) -> Any:
        """Get Calendar service (cached)."""
        if self._calendar_service is None:
            self._calendar_service = build("calendar", "v3", credentials=self._creds)
        return self._calendar_service

    def get_people_service(self) -> Any:
        """Get People API service."""
        return build("people", "v1", credentials=self._creds)

    def get_docs_service(self) -> Any:
        """Get Google Docs service (cached)."""
        if self._docs_service is None:
            self._docs_service = build("docs", "v1", credentials=self._creds)
        return self._docs_service

    def get_drive_service(self) -> Any:
        """Get Google Drive service (cached)."""
        if self._drive_service is None:
            self._drive_service = build("drive", "v3", credentials=self._creds)
        return self._drive_service
