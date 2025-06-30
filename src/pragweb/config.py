"""Configuration management for pragweb application.

This module loads configuration from environment variables with sensible defaults.
It uses dotenv to load from .env files and provides a centralized config object.
"""

import os
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


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


def load_default_config() -> AppConfig:
    """Load configuration from environment variables with defaults."""
    # Load environment variables from .env file
    load_dotenv()

    # Create config from environment variables with defaults
    page_cache_url = os.getenv("PAGE_CACHE_URL", "sqlite:///praga_cache.db")
    return AppConfig(
        server_root=os.getenv("SERVER_ROOT", "google"),
        page_cache_url=page_cache_url,
        secrets_database_url=os.getenv("SECRETS_DATABASE_URL", page_cache_url),
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
