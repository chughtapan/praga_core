"""Slack API authentication using singleton pattern."""

import logging
import os
import secrets
import subprocess
import tempfile
import threading
import time
import webbrowser
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

import uvicorn
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.oauth import AuthorizeUrlGenerator

from pragweb.config import get_current_config
from pragweb.secrets_manager import SecretsManager, get_secrets_manager

logger = logging.getLogger(__name__)

_DEFAULT_SCOPES = [
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "im:read",
    "im:history",
    "mpim:read",
    "mpim:history",
    "users:read",
    "users:read.email",
    "search:read",
]


class SlackOAuthServer:
    """Handles OAuth callback server for Slack authentication."""

    def __init__(self, port: int = 8787):
        self.port = port
        self.redirect_uri = f"https://localhost:{port}/slack/oauth/callback"

    def run_oauth_flow(self, auth_url: str, expected_state: str) -> Dict[str, Any]:
        """Run OAuth flow with callback server."""
        print("\nSlack OAuth Required:")
        print(f"Starting HTTPS server on localhost:{self.port}")
        print(
            "Your browser will show a security warning for the self-signed certificate"
        )
        print("Click 'Advanced' -> 'Proceed to localhost' to continue")
        print("Opening browser for authorization...")

        # Create result container
        oauth_result: Dict[str, Any] = {"code": None, "state": None, "error": None}

        # Create ASGI app
        asgi_app = self._create_asgi_app(oauth_result, expected_state)

        # Start server in background thread
        server_thread = threading.Thread(
            target=lambda: self._run_https_server(asgi_app)
        )
        server_thread.daemon = True
        server_thread.start()

        # Give server time to start
        time.sleep(3)

        # Open browser
        try:
            webbrowser.open(auth_url)
            print(f"Browser opened to: {auth_url}")
        except Exception as e:
            print(f"Could not open browser automatically: {e}")
            print(f"Please visit: {auth_url}")

        # Wait for callback
        return self._wait_for_callback(oauth_result)

    def _wait_for_callback(self, oauth_result: Dict[str, Any]) -> Dict[str, Any]:
        """Wait for OAuth callback with timeout."""
        print("Waiting for authorization...")
        timeout = 180  # 3 minutes
        start_time = time.time()

        while time.time() - start_time < timeout:
            if oauth_result["error"]:
                raise ValueError(f"OAuth failed: {oauth_result['error']}")
            if oauth_result["code"]:
                print("Authorization successful!")
                return {"code": oauth_result["code"], "state": oauth_result["state"]}
            time.sleep(0.5)

        raise ValueError("OAuth timeout - authorization not completed within 3 minutes")

    def _run_https_server(self, app: Callable[..., Any]) -> None:
        """Run uvicorn with self-signed HTTPS certificate."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cert_file = os.path.join(temp_dir, "cert.pem")
            key_file = os.path.join(temp_dir, "key.pem")

            # Generate self-signed certificate
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:4096",
                    "-keyout",
                    key_file,
                    "-out",
                    cert_file,
                    "-days",
                    "1",
                    "-nodes",
                    "-subj",
                    "/CN=localhost",
                ],
                check=True,
                capture_output=True,
            )

            # Run uvicorn with HTTPS
            uvicorn.run(
                app,
                host="localhost",
                port=self.port,
                ssl_keyfile=key_file,
                ssl_certfile=cert_file,
                log_level="error",
            )

    def _create_asgi_app(
        self, oauth_result: Dict[str, Any], expected_state: str
    ) -> Callable[..., Awaitable[None]]:
        """Create ASGI app to handle OAuth callbacks."""

        async def app(
            scope: Dict[str, Any],
            receive: Callable[..., Any],
            send: Callable[..., Awaitable[None]],
        ) -> None:
            if scope["type"] != "http":
                return

            path = scope["path"]
            query_string = scope.get("query_string", b"").decode()
            query_params = parse_qs(query_string)

            if path == "/slack/oauth/callback":
                await self._handle_oauth_callback(
                    oauth_result, expected_state, query_params, send
                )
            elif path == "/health":
                await self._handle_health(send)
            else:
                await self._handle_404(send)

        return app

    async def _handle_oauth_callback(
        self,
        oauth_result: Dict[str, Any],
        expected_state: str,
        query_params: Dict[str, List[str]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        """Handle OAuth callback."""
        # Check for error
        error = query_params.get("error", [None])[0]
        if error:
            error_desc = query_params.get("error_description", ["Unknown error"])[0]
            oauth_result["error"] = f"{error}: {error_desc}"

            await send(
                {
                    "type": "http.response.start",
                    "status": 400,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"status": "error", "message": "OAuth failed"}',
                }
            )
            return

        # Get code and state
        code = query_params.get("code", [None])[0]
        state = query_params.get("state", [None])[0]

        if not code:
            oauth_result["error"] = "No authorization code received"
            await self._send_error_response(send, "No authorization code received")
            return

        if state != expected_state:
            oauth_result["error"] = "Invalid state parameter"
            await self._send_error_response(send, "Invalid state parameter")
            return

        # Store results
        oauth_result["code"] = code
        oauth_result["state"] = state

        # Send success response
        await self._send_success_response(send)

    async def _send_error_response(
        self, send: Callable[..., Awaitable[None]], message: str
    ) -> None:
        """Send error response."""
        await send(
            {
                "type": "http.response.start",
                "status": 400,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": f'{{"status": "error", "message": "{message}"}}'.encode(),
            }
        )

    async def _send_success_response(
        self, send: Callable[..., Awaitable[None]]
    ) -> None:
        """Send success response."""
        success_html = """
        <html>
            <head><title>Slack OAuth Complete</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #4CAF50;">Authorization Successful!</h1>
                <p>You can now close this window and return to your application.</p>
                <script>
                    setTimeout(function() {
                        window.close();
                    }, 3000);
                </script>
            </body>
        </html>
        """.encode()

        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/html")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": success_html,
            }
        )

    async def _handle_health(self, send: Callable[..., Awaitable[None]]) -> None:
        """Handle health check."""
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"status": "ok"}',
            }
        )

    async def _handle_404(self, send: Callable[..., Awaitable[None]]) -> None:
        """Handle 404 responses."""
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"status": "not_found"}',
            }
        )


class SlackAuthManager:
    """Singleton Slack API authentication manager."""

    _instance: Optional["SlackAuthManager"] = None
    _initialized = False

    def __new__(cls) -> "SlackAuthManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._client: Optional[WebClient] = None
        self._token_data: Optional[Dict[str, Any]] = None
        self._authenticate()
        self._initialized = True

    def _get_credentials(self) -> Tuple[str, str]:
        """Get Slack client credentials from config."""
        config = get_current_config()

        if not config.slack_client_id or not config.slack_client_secret:
            raise ValueError(
                "Slack client credentials not configured. "
                "Please set SLACK_CLIENT_ID and SLACK_CLIENT_SECRET environment variables."
            )

        return config.slack_client_id, config.slack_client_secret

    def _load_token(self, secrets_manager: SecretsManager) -> Optional[Dict[str, Any]]:
        """Load existing Slack token from secrets manager."""
        token_data = secrets_manager.get_oauth_token("slack")
        if not token_data:
            logger.debug("No existing Slack token found")
            return None

        return {
            "access_token": token_data["access_token"],
            "token_type": token_data.get("token_type", "Bearer"),
            "scope": token_data.get("scopes", _DEFAULT_SCOPES),
            "user_id": token_data.get("extra_data", {}).get("user_id"),
            "team_id": token_data.get("extra_data", {}).get("team_id"),
            "team_name": token_data.get("extra_data", {}).get("team_name"),
        }

    def _store_token(
        self, token_data: Dict[str, Any], secrets_manager: SecretsManager
    ) -> None:
        """Store Slack token in secrets manager."""
        # Prepare extra data
        extra_data = {}
        if token_data.get("user_id"):
            extra_data["user_id"] = token_data["user_id"]
        if token_data.get("team_id"):
            extra_data["team_id"] = token_data["team_id"]
        if token_data.get("team_name"):
            extra_data["team_name"] = token_data["team_name"]

        # Store in secrets manager
        secrets_manager.store_oauth_token(
            service_name="slack",
            access_token=token_data["access_token"],
            refresh_token=None,  # Slack doesn't use refresh tokens
            token_type=token_data.get("token_type", "Bearer"),
            expires_at=None,  # Slack tokens don't expire
            scopes=token_data.get("scope", _DEFAULT_SCOPES),
            extra_data=extra_data if extra_data else None,
        )

    def _generate_auth_url(
        self, client_id: str, user_scopes: List[str], redirect_uri: str
    ) -> Tuple[str, str]:
        """Generate Slack OAuth authorization URL."""
        # Generate a random state for security
        state = secrets.token_urlsafe(32)

        # Create authorization URL
        auth_url_generator = AuthorizeUrlGenerator(
            client_id=client_id,
            scopes=[],
            user_scopes=user_scopes,
            redirect_uri=redirect_uri,
        )

        auth_url = auth_url_generator.generate(state=state)
        return auth_url, state

    def _exchange_code_for_token(
        self, code: str, client_id: str, client_secret: str
    ) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        # Use WebClient to make OAuth v2 access call
        oauth_client = WebClient()

        try:
            slack_response = oauth_client.oauth_v2_access(
                client_id=client_id, client_secret=client_secret, code=code
            )

            # Extract the actual data from SlackResponse object
            response_data = slack_response.data

            # Handle the case where response.data is bytes instead of dict
            if isinstance(response_data, bytes):
                raise ValueError(
                    "Unexpected response format: received bytes instead of dict"
                )

            # Now we can safely treat response_data as Dict[str, Any]
            response: Dict[str, Any] = response_data

            if not response.get("ok"):
                raise ValueError(f"OAuth exchange failed: {response.get('error')}")

            # For user scopes, the access token might be in authed_user instead of top level
            access_token = response.get("access_token")
            if not access_token and "authed_user" in response:
                authed_user = response["authed_user"]
                if isinstance(authed_user, dict):
                    access_token = authed_user.get("access_token")

            if not access_token:
                raise ValueError(
                    f"No access token found in response. Response keys: {list(response.keys())}"
                )

            # For user scopes, get the user scope from authed_user
            user_scope = None
            if "authed_user" in response and isinstance(response["authed_user"], dict):
                authed_user = response["authed_user"]
                if "scope" in authed_user:
                    user_scope = authed_user["scope"]
            elif response.get("scope"):
                user_scope = response.get("scope")

            scopes: List[str] = []
            if user_scope:
                scopes = (
                    user_scope.split(",") if isinstance(user_scope, str) else user_scope
                )
            else:
                scopes = _DEFAULT_SCOPES

            # Helper function to safely get nested dict values
            def get_nested_value(data: Dict[str, Any], *keys: str) -> Any:
                for key in keys:
                    if isinstance(data, dict) and key in data:
                        data = data[key]
                    else:
                        return None
                return data

            return {
                "access_token": access_token,
                "token_type": response.get("token_type", "Bearer"),
                "scope": scopes,
                "user_id": get_nested_value(response, "authed_user", "id"),
                "team_id": get_nested_value(response, "team", "id"),
                "team_name": get_nested_value(response, "team", "name"),
            }
        except Exception as e:
            raise ValueError(f"Failed to exchange code for token: {e}")

    def _run_oauth_flow(self) -> Dict[str, Any]:
        """Run the OAuth flow to get a new token using OAuth server."""
        client_id, client_secret = self._get_credentials()

        # Create OAuth server
        oauth_server = SlackOAuthServer()

        # Generate auth URL
        auth_url, state = self._generate_auth_url(
            client_id, _DEFAULT_SCOPES, oauth_server.redirect_uri
        )

        # Run OAuth flow with server
        callback_result = oauth_server.run_oauth_flow(auth_url, state)

        # Exchange code for token
        return self._exchange_code_for_token(
            callback_result["code"], client_id, client_secret
        )

    def _test_token(self, token: str) -> bool:
        """Test if a token is valid by making an API call."""
        try:
            client = WebClient(token=token)
            response = client.auth_test()
            return response.get("ok", False)
        except SlackApiError:
            return False

    def _authenticate(self) -> None:
        """Authenticate with Slack API."""
        config = get_current_config()
        secrets_manager = get_secrets_manager(config.secrets_database_url)

        # Try to load existing token
        self._token_data = self._load_token(secrets_manager)

        # Test token if it exists
        if self._token_data and self._token_data.get("access_token"):
            if self._test_token(self._token_data["access_token"]):
                self._client = WebClient(token=self._token_data["access_token"])
                logger.info("Successfully authenticated with existing Slack token")
                return
            else:
                logger.warning("Existing Slack token is invalid")
                self._token_data = None

        # Run OAuth flow to get new token
        try:
            self._token_data = self._run_oauth_flow()
            self._store_token(self._token_data, secrets_manager)
            self._client = WebClient(token=self._token_data["access_token"])
            logger.info("Successfully authenticated with new Slack token")
        except Exception as e:
            raise RuntimeError(f"Failed to authenticate with Slack: {e}")

    def get_client(self) -> WebClient:
        """Get authenticated Slack client."""
        if not self._client:
            raise RuntimeError(
                "Slack client not initialized. Authentication may have failed."
            )
        return self._client

    def get_token_data(self) -> Optional[Dict[str, Any]]:
        """Get current token data."""
        return self._token_data

    def refresh_token(self) -> None:
        """Refresh the token (re-run OAuth since Slack doesn't have refresh tokens)."""
        logger.info("Refreshing Slack token by re-running OAuth flow")
        config = get_current_config()
        secrets_manager = get_secrets_manager(config.secrets_database_url)

        try:
            self._token_data = self._run_oauth_flow()
            self._store_token(self._token_data, secrets_manager)
            self._client = WebClient(token=self._token_data["access_token"])
            logger.info("Successfully refreshed Slack token")
        except Exception as e:
            raise RuntimeError(f"Failed to refresh Slack token: {e}")

    def revoke_token(self) -> None:
        """Revoke the current token."""
        if not self._client or not self._token_data:
            return

        try:
            self._client.auth_revoke()
            logger.info("Successfully revoked Slack token")
        except SlackApiError as e:
            logger.warning(f"Failed to revoke token: {e}")
        finally:
            self._client = None
            self._token_data = None
