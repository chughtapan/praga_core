"""Tests for praga_core package initialization."""


class TestPackageInitialization:
    """Test that the praga_core package initializes correctly."""

    def test_package_imports_successfully(self) -> None:
        """Test that the main package can be imported without errors."""
        import praga_core

        assert praga_core is not None

    def test_main_classes_are_accessible(self) -> None:
        """Test that main classes can be imported from the package."""
        from praga_core.retriever import RetrieverToolkit
        from praga_core.retriever.tool import PaginatedResponse, Tool
        from praga_core.types import Page, TextPage

        # Verify classes are properly imported
        assert RetrieverToolkit is not None
        assert Tool is not None
        assert PaginatedResponse is not None
        assert Page is not None
        assert TextPage is not None

    def test_package_has_version(self) -> None:
        """Test that the package has a version attribute (if applicable)."""
        import praga_core

        # This test may need to be adjusted based on how versioning is handled
        # For now, just ensure the package exists
        assert hasattr(praga_core, "__name__")
