"""Secure secrets management for OAuth tokens and credentials."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import TIMESTAMP, String, Text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

logger = logging.getLogger(__name__)


# SQLAlchemy declarative base for secrets table
class Base(DeclarativeBase):
    pass


class OAuthToken(Base):
    """SQLAlchemy model for storing OAuth tokens."""

    __tablename__ = "oauth_tokens"

    # Service name as primary key (e.g., 'google', 'github', etc.)
    service_name: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Token data stored as JSON text
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_type: Mapped[str] = mapped_column(String(50), default="Bearer")
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Scopes granted to this token
    scopes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON string of scopes list

    # Additional token metadata as JSON
    extra_data: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # JSON string for any additional data

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SecretsManager:
    """Singleton secrets manager for secure OAuth token storage."""

    _instance: Optional["SecretsManager"] = None

    def __init__(self, database_url: str) -> None:
        """Initialize SecretsManager with database connection."""

        # Configure engine based on database type
        engine_args = {}
        if database_url.startswith("postgresql"):
            from sqlalchemy.pool import NullPool

            engine_args["poolclass"] = NullPool

        self._engine = create_engine(database_url, **engine_args)
        self._session_factory = sessionmaker(bind=self._engine)

        # Create tables if they don't exist
        Base.metadata.create_all(self._engine)

        logger.info("SecretsManager initialized with database")

    @property
    def engine(self) -> Engine:
        """Get the SQLAlchemy engine instance."""
        return self._engine

    def _get_session(self) -> Session:
        """Get a new database session."""
        return self._session_factory()

    def store_oauth_token(
        self,
        service_name: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_type: str = "Bearer",
        expires_at: Optional[datetime] = None,
        scopes: Optional[list[str]] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store or update OAuth token for a service.

        Args:
            service_name: Name of the service (e.g., 'google', 'github')
            access_token: The access token
            refresh_token: Optional refresh token
            token_type: Token type (default: 'Bearer')
            expires_at: Token expiration datetime
            scopes: List of granted scopes
            extra_data: Additional token metadata
        """
        import json

        with self._get_session() as session:
            # Check if token already exists
            existing_token = (
                session.query(OAuthToken).filter_by(service_name=service_name).first()
            )

            # Prepare scopes and extra_data as JSON strings
            scopes_json = json.dumps(scopes) if scopes else None
            extra_data_json = json.dumps(extra_data) if extra_data else None

            if existing_token:
                # Update existing token
                existing_token.access_token = access_token
                existing_token.refresh_token = refresh_token
                existing_token.token_type = token_type
                existing_token.expires_at = expires_at
                existing_token.scopes = scopes_json
                existing_token.extra_data = extra_data_json
                existing_token.updated_at = datetime.now(timezone.utc)
                logger.info(f"Updated OAuth token for service: {service_name}")
            else:
                # Create new token
                new_token = OAuthToken(
                    service_name=service_name,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_type=token_type,
                    expires_at=expires_at,
                    scopes=scopes_json,
                    extra_data=extra_data_json,
                )
                session.add(new_token)
                logger.info(f"Stored new OAuth token for service: {service_name}")

            session.commit()

    def get_oauth_token(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve OAuth token for a service.

        Args:
            service_name: Name of the service

        Returns:
            Dictionary containing token data or None if not found
        """
        import json

        with self._get_session() as session:
            token = (
                session.query(OAuthToken).filter_by(service_name=service_name).first()
            )

            if not token:
                return None

            # Parse JSON fields
            scopes = json.loads(token.scopes) if token.scopes else None
            extra_data = json.loads(token.extra_data) if token.extra_data else None

            return {
                "access_token": token.access_token,
                "refresh_token": token.refresh_token,
                "token_type": token.token_type,
                "expires_at": token.expires_at,
                "scopes": scopes,
                "extra_data": extra_data,
                "created_at": token.created_at,
                "updated_at": token.updated_at,
            }

    def delete_oauth_token(self, service_name: str) -> bool:
        """Delete OAuth token for a service.

        Args:
            service_name: Name of the service

        Returns:
            True if token was deleted, False if it didn't exist
        """
        with self._get_session() as session:
            token = (
                session.query(OAuthToken).filter_by(service_name=service_name).first()
            )

            if token:
                session.delete(token)
                session.commit()
                logger.info(f"Deleted OAuth token for service: {service_name}")
                return True
            else:
                logger.warning(f"No OAuth token found for service: {service_name}")
                return False

    def token_exists(self, service_name: str) -> bool:
        """Check if an OAuth token exists for a service.

        Args:
            service_name: Name of the service

        Returns:
            True if token exists, False otherwise
        """
        with self._get_session() as session:
            exists = (
                session.query(OAuthToken).filter_by(service_name=service_name).first()
            ) is not None
            return exists

    def is_token_expired(self, service_name: str) -> Optional[bool]:
        """Check if a token is expired.

        Args:
            service_name: Name of the service

        Returns:
            True if expired, False if valid, None if token doesn't exist
        """
        token_data = self.get_oauth_token(service_name)
        if not token_data:
            return None

        expires_at = token_data.get("expires_at")
        if not expires_at:
            # No expiration time means token doesn't expire
            return False

        now = datetime.now(timezone.utc)
        # Add small buffer (1 minute) to account for clock skew
        buffer_time = now.replace(second=now.second + 60)
        return bool(expires_at <= buffer_time)

    def list_services(self) -> list[str]:
        """Get list of all services with stored tokens.

        Returns:
            List of service names
        """
        with self._get_session() as session:
            services = session.query(OAuthToken.service_name).all()
            return [service[0] for service in services]


def get_secrets_manager(database_url: Optional[str] = None) -> SecretsManager:
    """Get the singleton SecretsManager instance.

    Args:
        database_url: Database URL (required for first initialization, ignored for subsequent calls)

    Returns:
        SecretsManager instance

    Raises:
        ValueError: If database_url is not provided for first initialization
    """
    if SecretsManager._instance is None:
        if database_url is None:
            raise ValueError("database_url is required for first initialization")

        # Create the singleton instance
        SecretsManager._instance = SecretsManager(database_url)
    else:
        # Instance already exists - database_url parameter is ignored
        if database_url is not None:
            logger.warning(
                "SecretsManager singleton already exists. "
                f"Ignoring database_url parameter: {database_url}"
            )

    return SecretsManager._instance
