"""Configuration for authentication."""

import os

# Base directories
SECRETS_DIR = os.path.expanduser("~/.praga/secrets")
os.makedirs(SECRETS_DIR, exist_ok=True)

# Google authentication
GOOGLE_CREDENTIALS_PATH = os.path.join(SECRETS_DIR, "google_credentials.json")
GOOGLE_TOKEN_PATH = os.path.join(SECRETS_DIR, "google_token.pickle")

# Slack authentication
SLACK_CREDENTIALS_PATH = os.path.join(SECRETS_DIR, "slack_credentials.json")
SLACK_TOKEN_PATH = os.path.join(SECRETS_DIR, "slack_token.json")
