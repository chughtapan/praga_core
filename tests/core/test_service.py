"""Tests for service infrastructure."""

from unittest.mock import Mock

import pytest

from praga_core import (
    ServerContext,
    Service,
    ServiceContext,
    clear_global_context,
    set_global_context,
)
from praga_core.agents import RetrieverToolkit


@pytest.fixture
async def service_context():
    clear_global_context()
    context = await ServerContext.create(root="test")
    set_global_context(context)
    yield context
    clear_global_context()


@pytest.fixture
async def server_context():
    context = await ServerContext.create(root="test")
    yield context


class TestService:
    """Tests for abstract Service class."""

    def test_service_is_abstract(self):
        """Test that Service cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Service()

    def test_service_requires_name_property(self):
        """Test that Service subclasses must implement name property."""

        class IncompleteService(Service):
            @property
            def toolkits(self):
                return []

        with pytest.raises(TypeError):
            IncompleteService()


class TestServiceContext:
    """Tests for ServiceContext auto-registration."""

    def test_service_context_auto_registers(self, service_context):
        """Test that ServiceContext automatically registers with global context."""

        class TestService(ServiceContext):
            @property
            def name(self):
                return "test_service"

            @property
            def toolkits(self):
                return []

        # Create service - should auto-register
        service = TestService()

        # Check it was registered
        assert "test_service" in service_context.services
        assert service_context.get_service("test_service") is service

    def test_service_context_with_api_client(self, service_context):
        """Test ServiceContext stores api_client properly."""

        class TestService(ServiceContext):
            @property
            def name(self):
                return "test_service"

            @property
            def toolkits(self):
                return []

        mock_client = Mock()
        service = TestService(api_client=mock_client)

        assert service.api_client is mock_client

    def test_service_context_without_api_client(self, service_context):
        """Test ServiceContext works without api_client."""

        class TestService(ServiceContext):
            @property
            def name(self):
                return "test_service"

            @property
            def toolkits(self):
                return []

        service = TestService()

        assert service.api_client is None

    def test_duplicate_service_registration_fails(self, service_context):
        """Test that registering duplicate service names fails."""

        class TestService(ServiceContext):
            @property
            def name(self):
                return "duplicate"

            @property
            def toolkits(self):
                return []

        # First registration should work
        _ = TestService()

        # Second registration should fail
        with pytest.raises(RuntimeError, match="Service already registered: duplicate"):
            _ = TestService()


class TestServerContextServiceRegistry:
    """Tests for ServerContext service registry functionality."""

    def test_register_service(self, server_context):
        """Test manual service registration."""
        mock_service = Mock(spec=Service)
        mock_service.name = "test_service"

        server_context.register_service("test_service", mock_service)

        assert "test_service" in server_context.services
        assert server_context.get_service("test_service") is mock_service

    def test_get_nonexistent_service_fails(self, server_context):
        """Test getting non-existent service raises error."""
        with pytest.raises(
            RuntimeError, match="No service registered with name: nonexistent"
        ):
            server_context.get_service("nonexistent")

    def test_services_property_returns_copy(self, server_context):
        """Test that services property returns a copy."""
        mock_service = Mock(spec=Service)
        server_context.register_service("test", mock_service)

        services_copy = server_context.services
        services_copy["new_service"] = Mock()

        # Original should be unchanged
        assert "new_service" not in server_context.services
        assert len(server_context.services) == 1

    def test_duplicate_manual_registration_fails(self, server_context):
        """Test manual duplicate registration fails."""
        mock_service1 = Mock(spec=Service)
        mock_service2 = Mock(spec=Service)

        server_context.register_service("duplicate", mock_service1)

        with pytest.raises(RuntimeError, match="Service already registered: duplicate"):
            server_context.register_service("duplicate", mock_service2)


class TestServiceIntegration:
    """Integration tests for service system."""

    def test_multiple_services_with_toolkits(self, service_context):
        """Test multiple services with toolkits."""

        # Mock toolkits
        toolkit1 = Mock(spec=RetrieverToolkit)
        toolkit2 = Mock(spec=RetrieverToolkit)
        toolkit3 = Mock(spec=RetrieverToolkit)

        class ServiceA(ServiceContext):
            @property
            def name(self):
                return "service_a"

            @property
            def toolkits(self):
                return [toolkit1]

        class ServiceB(ServiceContext):
            @property
            def name(self):
                return "service_b"

            @property
            def toolkits(self):
                return [toolkit2, toolkit3]  # Multiple toolkits

        # Create services
        service_a = ServiceA()
        service_b = ServiceB()

        # Check registration
        assert len(service_context.services) == 2
        assert service_context.get_service("service_a") is service_a
        assert service_context.get_service("service_b") is service_b

        # Check toolkits
        assert service_a.toolkits == [toolkit1]
        assert service_b.toolkits == [toolkit2, toolkit3]

        # Collect all toolkits (like app.py does)
        all_toolkits = []
        for service in service_context.services.values():
            all_toolkits.extend(service.toolkits)

        assert len(all_toolkits) == 3
        assert toolkit1 in all_toolkits
        assert toolkit2 in all_toolkits
        assert toolkit3 in all_toolkits
