"""Authentication package for Google and Slack APIs."""

from .google_auth import GoogleAuthManager
from .slack_auth import SlackAuthenticator

__all__ = ["GoogleAuthManager", "SlackAuthenticator"]
