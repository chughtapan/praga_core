"""Slack API authentication using OAuth2 flow and singleton pattern."""

import json
import logging
import os
from typing import Dict, Optional

from slack_sdk import WebClient
from slack_sdk.oauth import AuthorizeUrlGenerator
from slack_sdk.oauth.installation_store import FileInstallationStore, Installation
from slack_sdk.oauth.state_store import FileOAuthStateStore

from . import config

logger = logging.getLogger(__name__)

_DEFAULT_USER_SCOPES = [
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "im:read",
    "im:history",
    "mpim:read",
    "mpim:history",
    "users:read",
]

_DEFAULT_BOT_SCOPES = [
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "im:read",
    "im:history",
    "mpim:read",
    "mpim:history",
    "users:read",
]


class SlackAuthenticator:
    """Singleton Slack OAuth2 authentication manager."""

    _instance: Optional["SlackAuthenticator"] = None
    _initialized = False

    def __new__(
        cls,
        credentials_file: str = "",
        token_file: str = "",
        bot_scopes: list[str] = None,
        user_scopes: list[str] = None,
    ):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        credentials_file: str = "",
        token_file: str = "",
        bot_scopes: list[str] = None,
        user_scopes: list[str] = None,
    ):
        """Initialize Slack authenticator.

        Args:
            credentials_file: Path to file for storing client credentials
            token_file: Path to file for storing tokens
            bot_scopes: List of bot scopes to request
            user_scopes: List of user scopes to request
        """
        if self._initialized:
            return

        self.credentials_file = credentials_file or config.SLACK_CREDENTIALS_PATH
        self.token_file = token_file or config.SLACK_TOKEN_PATH
        self._token: Optional[Dict] = None

        self._load_credentials()

        self.bot_scopes = bot_scopes or _DEFAULT_BOT_SCOPES
        self.user_scopes = user_scopes or _DEFAULT_USER_SCOPES

        # Initialize OAuth components
        self.state_store = FileOAuthStateStore(
            expiration_seconds=300, base_dir=config.SECRETS_DIR
        )
        self.installation_store = FileInstallationStore(
            base_dir=os.path.dirname(self.token_file)
        )
        self.authorize_url_generator = AuthorizeUrlGenerator(
            client_id=self.client_id,
            scopes=self.bot_scopes,
            user_scopes=self.user_scopes,
        )

        self._client: Optional[WebClient] = None
        logger.debug("Initialized SlackAuthenticator")

        # Try to load existing token, refresh if needed
        if not self.load_token():
            self.refresh_token()

        self._initialized = True

    def _load_credentials(self) -> None:
        """Load credentials from file.

        Args:
            credentials_file: Path to credentials file
        """
        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"Slack credentials file not found: {self.credentials_file}\n"
                "Please create a Slack app and download the credentials."
            )

        with open(self.credentials_file) as f:
            creds = json.load(f)
            self.client_id = creds.get("client_id")
            self.client_secret = creds.get("client_secret")

        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "Invalid slack credentials file! client_id and client_secret must be set."
            )

    @property
    def token(self) -> Optional[Dict]:
        """Get the current token."""
        return self._token

    @property
    def client(self) -> Optional[WebClient]:
        """Get authenticated Slack client."""
        return self._client

    def load_token(self) -> bool:
        """Load token from file if it exists.

        Returns:
            bool: True if token was loaded successfully
        """
        try:
            # Try to load from installation store first
            installation = self.installation_store.find_installation(
                enterprise_id=None, team_id=None, is_enterprise_install=False
            )
            if installation:
                self._token = {
                    "access_token": installation.user_token,
                    "token_type": installation.token_type,
                    "scope": installation.user_scopes,
                    "user_id": installation.user_id,
                    "team_id": installation.team_id,
                }
                self._client = WebClient(token=self._token["access_token"])
                logger.debug("Loaded token from installation store")
                return True

            # Fall back to token file
            if os.path.exists(self.token_file):
                with open(self.token_file) as f:
                    self._token = json.load(f)
                    assert self._token is not None
                    self._client = WebClient(token=self._token["access_token"])
                    logger.debug("Loaded token from %s", self.token_file)
                    return True
        except Exception as e:
            logger.error("Failed to load token: %s", e)
            self._token = None
            self._client = None
        return False

    def save_token(self) -> None:
        """Save current token to file."""
        if not self._token:
            return
        try:
            # Save to installation store
            token_dict = self._token  # Create a reference to avoid multiple None checks
            if not isinstance(token_dict, dict):
                logger.error("Token is not a dictionary")
                return

            installation = Installation(
                app_id=str(token_dict.get("app_id", "")),
                enterprise_id=None,
                team_id=str(token_dict.get("team_id", "")),
                user_id=str(token_dict.get("user_id", "")),
                user_token=str(token_dict["access_token"]),
                user_scopes=token_dict.get("scope", ""),
                token_type=token_dict.get("token_type", "user"),
                is_enterprise_install=False,
            )
            self.installation_store.save(installation)

            # Also save to token file as backup
            with open(self.token_file, "w") as f:
                json.dump(token_dict, f, indent=2)
            logger.debug("Saved token to installation store and %s", self.token_file)
        except Exception as e:
            logger.error("Failed to save token: %s", e)

    def refresh_token(self) -> None:
        if self._token:
            return
        logger.info("No valid token found, starting OAuth flow...")
        self._run_oauth_flow()
        self.save_token()

    def _run_oauth_flow(self) -> None:
        """Run OAuth2 flow to get new token."""
        # Generate state parameter and authorization URL
        state = self.state_store.issue()
        auth_url = self.authorize_url_generator.generate(state)

        print("\nPlease visit this URL to authorize the application:")
        print(f"\n{auth_url}\n")
        print(
            "After authorizing, you will be redirected to a page that says 'This site can't be reached'"
        )
        print("Copy the entire URL from your browser's address bar and paste it here.")
        print("\nPaste the URL here: ", end="", flush=True)

        redirect_url = input().strip()

        # Extract code from the redirect URL
        try:
            from urllib.parse import parse_qs, urlparse

            parsed = urlparse(redirect_url)
            params = parse_qs(parsed.query)
            code = params.get("code", [""])[0]
            response_state = params.get("state", [""])[0]

            if not code:
                raise ValueError("No code found in redirect URL")

            # Verify state parameter
            if not self.state_store.consume(response_state):
                raise RuntimeError("Invalid state parameter in OAuth callback")

        except Exception as e:
            logger.error("Failed to parse redirect URL: %s", e)
            raise RuntimeError("Invalid redirect URL")

        # Exchange the code for a token using WebClient
        client = WebClient()
        try:
            oauth_response = client.oauth_v2_access(
                client_id=self.client_id, client_secret=self.client_secret, code=code
            )

            # Store the token information
            self._token = {
                "access_token": oauth_response["authed_user"]["access_token"],
                "token_type": oauth_response.get("token_type", "user"),
                "scope": oauth_response["authed_user"].get("scope", ""),
                "user_id": oauth_response["authed_user"]["id"],
                "team_id": oauth_response["team"]["id"],
                "app_id": oauth_response.get("app_id"),
            }

            self._client = WebClient(token=self._token["access_token"])
            logger.info("Successfully completed OAuth flow")

        except Exception as e:
            logger.error("Failed to complete OAuth flow: %s", e)
            raise

    def get_client(self) -> WebClient:
        """Get authenticated Slack WebClient."""
        if not self._client:
            logger.info("No authenticated client found, attempting to refresh token...")
            self.refresh_token()
            if not self._client:
                raise RuntimeError(
                    "Slack client not authenticated. Please run refresh_token()."
                )
        return self._client
