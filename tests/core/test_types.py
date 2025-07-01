"""Tests for JSON serialization of types with PageURI encoders.

This module tests the JSON serialization behavior of PageURI, Page, PageReference,
and related classes with the new json_encoders configuration.
"""

import json

from praga_core.types import PageReference, PageURI, SearchResponse, TextPage, DEFAULT_VERSION


class TestPageURIJSONSerialization:
    """Test PageURI JSON serialization behavior."""

    def test_page_uri_direct_json_serialization(self) -> None:
        """Test that PageURI can be serialized directly to JSON string."""
        uri = PageURI(root="test", type="Email", id="123", version=2)

        serialized = uri.model_dump(mode="json")
        expected = "test/Email:123@2"
        assert serialized == expected

    def test_page_uri_string_representation(self) -> None:
        """Test PageURI string representation."""
        uri = PageURI(root="myserver", type="Document", id="abc", version=2)
        assert str(uri) == "myserver/Document:abc@2"

    def test_page_uri_default_version_serialization(self) -> None:
        """Test that default version PageURI serializes without version number."""
        uri = PageURI(root="test", type="Email", id="123", version=DEFAULT_VERSION)

        serialized = uri.model_dump(mode="json")
        expected = "test/Email:123"
        assert serialized == expected

    def test_page_uri_default_version_string_representation(self) -> None:
        """Test default version PageURI string representation."""
        uri = PageURI(root="myserver", type="Document", id="abc", version=DEFAULT_VERSION)
        assert str(uri) == "myserver/Document:abc"

    def test_page_uri_default_version_default(self) -> None:
        """Test that PageURI defaults to default version."""
        uri = PageURI(root="test", type="Email", id="123")
        assert uri.version == DEFAULT_VERSION
        assert str(uri) == "test/Email:123"

    def test_page_uri_default_version_parsing(self) -> None:
        """Test parsing URI string without version defaults to default version."""
        uri = PageURI.parse("test/Email:123")
        assert uri.version == DEFAULT_VERSION

    def test_page_uri_version_validation(self) -> None:
        """Test that invalid version numbers are rejected."""
        import pytest
        
        # Test negative version
        with pytest.raises(ValueError, match="Version must be non-negative"):
            PageURI(root="test", type="Email", id="123", version=-1)


class TestPageJSONSerialization:
    """Test Page JSON serialization with PageURI encoder."""

    def test_text_page_json_serialization(self) -> None:
        """Test that TextPage serializes PageURI as string."""
        page = TextPage(
            uri=PageURI(root="test", type="TextPage", id="doc1", version=1),
            content="Test content",
        )

        serialized = page.model_dump(mode="json")

        # URI should be serialized as string due to json_encoders
        assert serialized["uri"] == "test/TextPage:doc1@1"
        assert serialized["content"] == "Test content"
        assert isinstance(serialized["uri"], str)

    def test_text_page_json_dumps(self) -> None:
        """Test that TextPage can be JSON dumped."""
        page = TextPage(
            uri=PageURI(root="test", type="TextPage", id="doc1", version=1),
            content="Test content",
        )

        json_str = json.dumps(page.model_dump(mode="json"))
        parsed = json.loads(json_str)

        assert parsed["uri"] == "test/TextPage:doc1@1"
        assert parsed["content"] == "Test content"

    def test_page_with_complex_uri(self) -> None:
        """Test Page serialization with complex URI values."""
        page = TextPage(
            uri=PageURI(
                root="complex-server", type="EmailMessage", id="msg_12345", version=3
            ),
            content="Complex test content",
        )

        serialized = page.model_dump(mode="json")
        assert serialized["uri"] == "complex-server/EmailMessage:msg_12345@3"


class TestPageReferenceJSONSerialization:
    """Test PageReference JSON serialization with PageURI encoder."""

    def test_page_reference_json_serialization(self) -> None:
        """Test that PageReference serializes PageURI as string."""
        ref = PageReference(
            uri=PageURI(root="test", type="Document", id="ref1", version=1),
            score=0.95,
            explanation="Test reference",
        )

        serialized = ref.model_dump(mode="json")

        assert serialized["uri"] == "test/Document:ref1@1"
        assert serialized["score"] == 0.95
        assert serialized["explanation"] == "Test reference"
        assert isinstance(serialized["uri"], str)

    def test_page_reference_json_dumps(self) -> None:
        """Test that PageReference can be JSON dumped."""
        ref = PageReference(
            uri=PageURI(root="server", type="Email", id="email123", version=2),
            score=0.88,
            explanation="Email reference",
        )

        json_str = json.dumps(ref.model_dump(mode="json"))
        parsed = json.loads(json_str)

        assert parsed["uri"] == "server/Email:email123@2"
        assert parsed["score"] == 0.88
        assert parsed["explanation"] == "Email reference"


class TestSearchResponseJSONSerialization:
    """Test SearchResponse JSON serialization with nested PageReference objects."""

    def test_search_response_json_serialization(self) -> None:
        """Test that SearchResponse properly serializes nested PageReference objects."""
        refs = [
            PageReference(
                uri=PageURI(root="test", type="Doc", id="doc1", version=1),
                score=0.9,
                explanation="First doc",
            ),
            PageReference(
                uri=PageURI(root="test", type="Doc", id="doc2", version=1),
                score=0.8,
                explanation="Second doc",
            ),
        ]

        response = SearchResponse(results=refs)
        serialized = response.model_dump(mode="json")

        assert len(serialized["results"]) == 2
        assert serialized["results"][0]["uri"] == "test/Doc:doc1@1"
        assert serialized["results"][1]["uri"] == "test/Doc:doc2@1"
        assert serialized["results"][0]["score"] == 0.9
        assert serialized["results"][1]["score"] == 0.8

    def test_search_response_json_dumps(self) -> None:
        """Test that SearchResponse can be JSON dumped."""
        refs = [
            PageReference(
                uri=PageURI(root="server", type="Email", id="email1", version=1),
                score=0.95,
                explanation="Top email result",
            )
        ]

        response = SearchResponse(results=refs)
        json_str = json.dumps(response.model_dump(mode="json"))
        parsed = json.loads(json_str)

        assert len(parsed["results"]) == 1
        assert parsed["results"][0]["uri"] == "server/Email:email1@1"
        assert parsed["results"][0]["score"] == 0.95
        assert parsed["results"][0]["explanation"] == "Top email result"


class TestJSONEncoderConsistency:
    """Test consistency of JSON encoding across different scenarios."""

    def test_nested_page_reference_in_page(self) -> None:
        """Test that PageURI is consistently encoded when nested in different contexts."""
        # Create a page with a complex URI
        page = TextPage(
            uri=PageURI(root="main", type="TextDocument", id="complex_doc", version=5),
            content="Document content",
        )

        # Create a reference to the same URI
        ref = PageReference(
            uri=PageURI(root="main", type="TextDocument", id="complex_doc", version=5),
            score=1.0,
            explanation="Same document reference",
        )

        page_serialized = page.model_dump(mode="json")
        ref_serialized = ref.model_dump(mode="json")

        # Both should serialize the URI identically
        expected_uri = "main/TextDocument:complex_doc@5"
        assert page_serialized["uri"] == expected_uri
        assert ref_serialized["uri"] == expected_uri

    def test_empty_root_uri_serialization(self) -> None:
        """Test serialization of PageURI with empty root."""
        page = TextPage(
            uri=PageURI(root="", type="LocalDoc", id="local1", version=1),
            content="Local content",
        )

        serialized = page.model_dump(mode="json")
        assert serialized["uri"] == "/LocalDoc:local1@1"

    def test_json_encoder_preserves_other_fields(self) -> None:
        """Test that JSON encoder doesn't interfere with other field serialization."""
        ref = PageReference(
            uri=PageURI(root="test", type="Mixed", id="mixed1", version=1),
            score=0.75,
            explanation="Mixed content test",
        )

        serialized = ref.model_dump(mode="json")

        # Verify all fields are present and correctly typed
        assert isinstance(serialized["uri"], str)
        assert isinstance(serialized["score"], float)
        assert isinstance(serialized["explanation"], str)
        assert serialized["uri"] == "test/Mixed:mixed1@1"
        assert serialized["score"] == 0.75
        assert serialized["explanation"] == "Mixed content test"


class TestBackwardCompatibility:
    """Test that the JSON encoder changes don't break existing functionality."""

    def test_page_uri_parsing_still_works(self) -> None:
        """Test that PageURI.parse still works with serialized URIs."""
        original_uri = PageURI(root="compat", type="TestDoc", id="compat1", version=2)

        # Serialize through a Page object
        page = TextPage(uri=original_uri, content="Compatibility test")
        serialized = page.model_dump(mode="json")

        # Parse the serialized URI string back
        parsed_uri = PageURI.parse(serialized["uri"])

        assert parsed_uri == original_uri
        assert parsed_uri.root == "compat"
        assert parsed_uri.type == "TestDoc"
        assert parsed_uri.id == "compat1"
        assert parsed_uri.version == 2

    def test_page_reference_with_page_assignment(self) -> None:
        """Test that PageReference with assigned page still serializes correctly."""
        uri = PageURI(root="test", type="AssignedDoc", id="assigned1", version=1)
        page = TextPage(uri=uri, content="Assigned page content")

        ref = PageReference(uri=uri, score=0.85, explanation="Assigned page ref")
        ref.page = page  # Assign the page

        # Serialization should still work correctly
        serialized = ref.model_dump(mode="json")
        assert serialized["uri"] == "test/AssignedDoc:assigned1@1"
        assert serialized["score"] == 0.85

        # Verify the page is still accessible
        assert ref.page.content == "Assigned page content"
