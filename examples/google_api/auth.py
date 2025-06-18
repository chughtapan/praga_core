"""Google API authentication using singleton pattern."""

import os
import pickle
from typing import Optional

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",  # For People API
    "https://www.googleapis.com/auth/directory.readonly",
]


class GoogleAuthManager:
    """Singleton Google API authentication manager."""

    _instance: Optional["GoogleAuthManager"] = None
    _initialized = False

    def __new__(cls, secrets_dir: str = ""):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, secrets_dir: str = ""):
        if self._initialized:
            return

        self.secrets_dir = secrets_dir
        self._creds = None
        self._gmail_service = None
        self._calendar_service = None
        self._authenticate()
        self._initialized = True

    def _get_credentials_path(self) -> str:
        """Get path to credentials file."""
        if self.secrets_dir:
            return os.path.join(self.secrets_dir, "credentials.json")
        return "credentials.json"

    def _get_token_path(self) -> str:
        """Get path to token file."""
        if self.secrets_dir:
            return os.path.join(self.secrets_dir, "token.pickle")
        return "token.pickle"

    def _authenticate(self) -> None:
        """Authenticate with Google APIs."""
        token_path = self._get_token_path()

        # Load existing token
        if os.path.exists(token_path):
            with open(token_path, "rb") as token:
                self._creds = pickle.load(token)

        # If no valid credentials, get new ones
        if not self._creds or not self._creds.valid:
            if self._creds and self._creds.expired and self._creds.refresh_token:
                self._creds.refresh(Request())
            else:
                credentials_path = self._get_credentials_path()
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, _SCOPES
                )
                self._creds = flow.run_local_server(port=0)

            # Save credentials for next run
            with open(token_path, "wb") as token:
                pickle.dump(self._creds, token)

    def get_gmail_service(self):
        """Get Gmail service (cached)."""
        if self._gmail_service is None:
            self._gmail_service = build("gmail", "v1", credentials=self._creds)
        return self._gmail_service

    def get_calendar_service(self):
        """Get Calendar service (cached)."""
        if self._calendar_service is None:
            self._calendar_service = build("calendar", "v3", credentials=self._creds)
        return self._calendar_service

    def get_people_service(self):
        """Get People API service."""
        return build("people", "v1", credentials=self._creds)
