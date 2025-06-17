"""Google API authentication utilities."""

import os
import pickle
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class GoogleAuthManager:
    """Manages Google API authentication and service creation."""

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/contacts.readonly",  # For People API
        "https://www.googleapis.com/auth/directory.readonly",
    ]

    def __init__(self, secrets_dir: Optional[str] = None):
        """Initialize the auth manager with optional custom secrets directory."""
        if not secrets_dir:
            secrets_dir = os.path.expanduser("~/.praga_secrets")

        self.secrets_dir = Path(secrets_dir)
        self.secrets_dir.mkdir(exist_ok=True)

        self.credentials_file = self.secrets_dir / "credentials.json"
        self.token_file = self.secrets_dir / "token.pickle"

    def get_credentials(self) -> Credentials:
        """Get valid Google API credentials, performing OAuth flow if needed."""
        creds = None

        # Load existing token if available
        if self.token_file.exists():
            with open(self.token_file, "rb") as token:
                creds = pickle.load(token)

        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"Google OAuth credentials file not found at {self.credentials_file}. "
                        f"Please download your OAuth client credentials from the Google Cloud Console "
                        f"and save them as 'credentials.json' in {self.secrets_dir}"
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), self.SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            with open(self.token_file, "wb") as token:
                pickle.dump(creds, token)

        return creds

    def get_service(self, service_name: str, version: str):
        """Create and return a Google API service."""
        creds = self.get_credentials()
        return build(service_name, version, credentials=creds)

    def get_gmail_service(self):
        """Get Gmail API service."""
        return self.get_service("gmail", "v1")

    def get_calendar_service(self):
        """Get Calendar API service."""
        return self.get_service("calendar", "v3")

    def get_people_service(self):
        """Get People API service."""
        return self.get_service("people", "v1")
