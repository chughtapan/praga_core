"""Configuration management for pragweb application.

This module loads configuration from environment variables with sensible defaults.
It uses dotenv to load from .env files and provides a centralized config object.
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class AppConfig(BaseModel):
    """Application configuration loaded from environment variables."""

    # Server Configuration
    server_root: str = Field(description="Root identifier for the server context")

    # Database and Cache Configuration
    page_cache_url: str = Field(description="Database URL for page cache storage")
    secrets_database_url: str = Field(
        description="Database URL for secrets storage",
    )

    # AI/Agent Configuration
    retriever_agent_model: str = Field(
        description="OpenAI model to use for the retriever agent"
    )
    retriever_max_iterations: int = Field(
        description="Maximum iterations for the retriever agent"
    )

    # API Keys
    openai_api_key: str = Field(description="OpenAI API key (required)")

    # Google API Configuration
    google_credentials_file: str = Field(
        description="Path to Google API credentials file"
    )

    # Logging Configuration
    log_level: str = Field(description="Logging level")

    @field_validator("openai_api_key")
    @classmethod
    def validate_openai_api_key(cls, v: str) -> str:
        """Validate that OpenAI API key is provided."""
        if not v:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required. "
                "Please set it in your .env file or environment."
            )
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate and normalize log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        level = v.upper()
        if level not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return level

    @field_validator("retriever_max_iterations")
    @classmethod
    def validate_max_iterations(cls, v: int) -> int:
        """Validate max iterations is positive."""
        if v <= 0:
            raise ValueError("retriever_max_iterations must be positive")
        return v


def detect_environment() -> str:
    """Detect the current runtime environment.

    Returns:
        'smithery': Running in Smithery cloud environment
        'ci': Running in CI/testing environment
        'user': Running in user/development environment
    """
    # Check for Smithery environment
    if os.getenv("SMITHERY") or os.getenv("SMITHERY_DEPLOYMENT"):
        return "smithery"

    # Check for CI/testing environment
    if os.getenv("CI") or os.getenv("PYTEST_CURRENT_TEST"):
        return "ci"

    # Default to user environment
    return "user"


def get_database_urls(environment: str) -> tuple[str, str]:
    """Get appropriate database URLs based on environment.

    Args:
        environment: The detected environment type

    Returns:
        Tuple of (page_cache_url, secrets_database_url)
    """
    # Check for explicit environment variable overrides first
    explicit_page_cache = os.getenv("PAGE_CACHE_URL")
    explicit_secrets = os.getenv("SECRETS_DATABASE_URL")

    if explicit_page_cache and explicit_secrets:
        logger.info(f"Using explicit database URLs for {environment} environment")
        return (explicit_page_cache, explicit_secrets)

    # Use environment-specific defaults
    if environment in ("smithery", "ci"):
        # Use in-memory databases for ephemeral environments
        in_memory_url = "sqlite+aiosqlite:///:memory:"
        logger.info(f"Using in-memory databases for {environment} environment")
        return (in_memory_url, in_memory_url)
    else:
        # Use persistent databases for user environments
        page_cache_url = explicit_page_cache or "sqlite+aiosqlite:///praga_cache.db"
        secrets_url = explicit_secrets or page_cache_url
        logger.info(f"Using persistent databases for {environment} environment")
        return (page_cache_url, secrets_url)


def load_default_config() -> AppConfig:
    """Load configuration from environment variables with defaults."""
    # Load environment variables from .env file
    load_dotenv()

    # Detect environment and get appropriate database URLs
    environment = detect_environment()
    page_cache_url, secrets_database_url = get_database_urls(environment)

    return AppConfig(
        server_root=os.getenv("SERVER_ROOT", "google"),
        page_cache_url=page_cache_url,
        secrets_database_url=secrets_database_url,
        retriever_agent_model=os.getenv("RETRIEVER_AGENT_MODEL", "gpt-4o-mini"),
        retriever_max_iterations=int(os.getenv("RETRIEVER_MAX_ITERATIONS", "10")),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        google_credentials_file=os.getenv(
            "GOOGLE_CREDENTIALS_FILE", "credentials.json"
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


# Singleton config instance
_config: Optional[AppConfig] = None


def get_current_config() -> AppConfig:
    """Get the current application configuration (singleton)."""
    global _config
    if _config is None:
        _config = load_default_config()
    return _config
