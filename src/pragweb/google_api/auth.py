"""Google API authentication using singleton pattern."""

import logging
import os
import threading
from datetime import timezone
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]
from googleapiclient.discovery import build  # type: ignore[import-untyped]

from pragweb.config import get_current_config
from pragweb.secrets_manager import SecretsManager, get_secrets_manager

logger = logging.getLogger(__name__)

# Thread-local storage to safely cache per-thread Google service objects.
_thread_local = threading.local()

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
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
        self._authenticate()
        self._initialized = True

    def _get_credentials_path(self) -> str:
        """Get path to credentials file."""
        return get_current_config().google_credentials_file

    def _create_credentials_from_env(self) -> Optional[Credentials]:
        """Create credentials from environment variables if available."""
        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
        refresh_token = os.environ.get("GOOGLE_OAUTH_REFRESH_TOKEN")

        if not all([client_id, client_secret, refresh_token]):
            return None

        logger.info("Creating Google credentials from environment variables")

        # Create credentials object with refresh token
        creds = Credentials(  # type: ignore[no-untyped-call]
            token=None,  # Will be populated on first refresh
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=_SCOPES,
        )

        # Refresh to get an access token
        try:
            creds.refresh(Request())  # type: ignore[no-untyped-call]
            return creds
        except Exception as e:
            logger.error(f"Failed to refresh token from environment variables: {e}")
            return None

    def _scopes_match(
        self, stored_scopes: list[str], required_scopes: list[str]
    ) -> bool:
        """Check if stored scopes contain all required scopes."""
        return set(required_scopes).issubset(set(stored_scopes))

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
        stored_scopes = token_data.get("scopes", _SCOPES)

        # Check if stored scopes match required scopes
        if not self._scopes_match(stored_scopes, _SCOPES):
            logger.info(
                f"Stored scopes {stored_scopes} don't match required scopes {_SCOPES}. "
                "Forcing reauth."
            )
            return None

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
            scopes=stored_scopes,
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
        # First try to create credentials from environment variables
        self._creds = self._create_credentials_from_env()

        if self._creds and self._creds.valid:
            logger.info("Successfully authenticated using environment variables")
            return

        # Fall back to secrets manager
        config = get_current_config()
        secrets_manager = get_secrets_manager(config.secrets_database_url)

        self._creds = self._load_credentials(secrets_manager)
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())  # type: ignore[no-untyped-call]
                self._store_credentials(self._creds, secrets_manager)
            else:
                # Fall back to file-based OAuth flow
                try:
                    credentials_path = self._get_credentials_path()
                    flow = InstalledAppFlow.from_client_secrets_file(
                        credentials_path, _SCOPES
                    )
                    self._creds = flow.run_local_server(port=0)
                    # Save new credentials
                    self._store_credentials(self._creds, secrets_manager)
                except Exception as e:
                    logger.error(f"Failed to authenticate with Google APIs: {e}")
                    raise RuntimeError(
                        "Unable to authenticate with Google APIs. "
                        "Please provide either environment variables "
                        "(GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN) "
                        "or a valid credentials file."
                    )

    def get_gmail_service(self) -> Any:
        """Get Gmail service (cached)."""
        # Use thread-local cache to avoid sharing httplib2.Http across threads.
        if not hasattr(_thread_local, "gmail_service"):
            _thread_local.gmail_service = build("gmail", "v1", credentials=self._creds)
        return _thread_local.gmail_service

    def get_calendar_service(self) -> Any:
        """Get Calendar service (cached)."""
        if not hasattr(_thread_local, "calendar_service"):
            _thread_local.calendar_service = build(
                "calendar", "v3", credentials=self._creds
            )
        return _thread_local.calendar_service

    def get_people_service(self) -> Any:
        """Get People API service."""
        if not hasattr(_thread_local, "people_service"):
            _thread_local.people_service = build(
                "people", "v1", credentials=self._creds
            )
        return _thread_local.people_service

    def get_docs_service(self) -> Any:
        """Get Google Docs service (cached)."""
        if not hasattr(_thread_local, "docs_service"):
            _thread_local.docs_service = build("docs", "v1", credentials=self._creds)
        return _thread_local.docs_service

    def get_drive_service(self) -> Any:
        """Get Google Drive service (cached)."""
        if not hasattr(_thread_local, "drive_service"):
            _thread_local.drive_service = build("drive", "v3", credentials=self._creds)
        return _thread_local.drive_service
