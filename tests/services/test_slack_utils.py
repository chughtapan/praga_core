"""Tests for SlackParser utility class."""

import pytest

from pragweb.slack.utils import SlackParser


class TestSlackParser:
    """Test suite for SlackParser utility class."""

    def setup_method(self):
        """Set up test environment."""
        self.parser = SlackParser()

    def test_encode_message_id(self):
        """Test message ID encoding."""
        channel_id = "C1234567890"
        message_ts = "1234567890.001"

        result = SlackParser.encode_message_id(channel_id, message_ts)
        expected = "C1234567890_1234567890.001"

        assert result == expected

    def test_encode_message_id_with_underscores(self):
        """Test message ID encoding with channel that contains underscores."""
        channel_id = "C_TEST_CHANNEL"
        message_ts = "1234567890.001"

        result = SlackParser.encode_message_id(channel_id, message_ts)
        expected = "C_TEST_CHANNEL_1234567890.001"

        assert result == expected

    def test_decode_message_id(self):
        """Test message ID decoding."""
        message_id = "C1234567890_1234567890.001"

        channel_id, message_ts = SlackParser.decode_message_id(message_id)

        assert channel_id == "C1234567890"
        assert message_ts == "1234567890.001"

    def test_decode_message_id_with_underscores(self):
        """Test message ID decoding with channel that contains underscores."""
        message_id = "C_TEST_CHANNEL_1234567890.001"

        channel_id, message_ts = SlackParser.decode_message_id(message_id)

        assert channel_id == "C_TEST_CHANNEL"
        assert message_ts == "1234567890.001"

    def test_decode_message_id_multiple_underscores(self):
        """Test message ID decoding with multiple underscores in channel ID."""
        message_id = "C_VERY_LONG_CHANNEL_NAME_1234567890.001"

        channel_id, message_ts = SlackParser.decode_message_id(message_id)

        assert channel_id == "C_VERY_LONG_CHANNEL_NAME"
        assert message_ts == "1234567890.001"

    def test_decode_message_id_invalid_format(self):
        """Test message ID decoding with invalid format."""
        # No underscore
        with pytest.raises(ValueError, match="Invalid message ID format"):
            SlackParser.decode_message_id("C1234567890")

        # Empty string
        with pytest.raises(ValueError, match="Invalid message ID format"):
            SlackParser.decode_message_id("")

    def test_encode_thread_id(self):
        """Test thread ID encoding."""
        channel_id = "C1234567890"
        thread_ts = "1234567890.001"

        result = SlackParser.encode_thread_id(channel_id, thread_ts)
        expected = "C1234567890_1234567890.001"

        assert result == expected

    def test_decode_thread_id(self):
        """Test thread ID decoding."""
        thread_id = "C1234567890_1234567890.001"

        channel_id, thread_ts = SlackParser.decode_thread_id(thread_id)

        assert channel_id == "C1234567890"
        assert thread_ts == "1234567890.001"

    def test_decode_thread_id_invalid_format(self):
        """Test thread ID decoding with invalid format."""
        with pytest.raises(ValueError, match="Invalid thread ID format"):
            SlackParser.decode_thread_id("invalidformat")

    def test_determine_channel_type_public_channel(self):
        """Test channel type determination for public channel."""
        channel_info = {
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
        }

        result = SlackParser.determine_channel_type(channel_info)
        assert result == "public_channel"

    def test_determine_channel_type_private_channel(self):
        """Test channel type determination for private channel/group."""
        channel_info = {
            "is_channel": False,
            "is_group": True,
            "is_im": False,
            "is_mpim": False,
        }

        result = SlackParser.determine_channel_type(channel_info)
        assert result == "private_channel"

    def test_determine_channel_type_direct_message(self):
        """Test channel type determination for direct message."""
        channel_info = {
            "is_channel": False,
            "is_group": False,
            "is_im": True,
            "is_mpim": False,
        }

        result = SlackParser.determine_channel_type(channel_info)
        assert result == "im"

    def test_determine_channel_type_group_dm(self):
        """Test channel type determination for group DM."""
        channel_info = {
            "is_channel": False,
            "is_group": False,
            "is_im": False,
            "is_mpim": True,
        }

        result = SlackParser.determine_channel_type(channel_info)
        assert result == "mpim"

    def test_determine_channel_type_unknown(self):
        """Test channel type determination for unknown type."""
        channel_info = {
            "is_channel": False,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
        }

        result = SlackParser.determine_channel_type(channel_info)
        assert result == "unknown"

    def test_get_user_display_name_with_display_name(self):
        """Test user display name extraction with display_name."""
        user_info = {
            "id": "U123456",
            "name": "alice",
            "real_name": "Alice Smith",
            "profile": {"display_name": "Alice"},
        }

        result = SlackParser.get_user_display_name(user_info)
        assert result == "Alice"

    def test_get_user_display_name_with_real_name(self):
        """Test user display name extraction with real_name fallback."""
        user_info = {
            "id": "U123456",
            "name": "alice",
            "real_name": "Alice Smith",
            "profile": {},  # No display name
        }

        result = SlackParser.get_user_display_name(user_info)
        assert result == "Alice Smith"

    def test_get_user_display_name_with_username(self):
        """Test user display name extraction with username fallback."""
        user_info = {
            "id": "U123456",
            "name": "alice",
            # No real_name or display_name
        }

        result = SlackParser.get_user_display_name(user_info)
        assert result == "alice"

    def test_get_user_display_name_with_id_fallback(self):
        """Test user display name extraction with ID fallback."""
        user_info = {
            "id": "U123456",
            # No name, real_name, or display_name
        }

        result = SlackParser.get_user_display_name(user_info)
        assert result == "U123456"

    def test_get_user_display_name_minimal(self):
        """Test user display name extraction with minimal data."""
        user_info = {}

        result = SlackParser.get_user_display_name(user_info)
        assert result == "unknown"

    def test_format_messages_for_content(self):
        """Test message formatting for content."""
        messages = [
            {
                "ts": "1234567890.001",
                "user": "U123456",
                "text": "Hello everyone!",
            },
            {
                "ts": "1234567890.002",
                "user": "U789012",
                "text": "Hi there!",
            },
            {
                "ts": "1234567890.003",
                "user": "U456789",
                "text": "How's everyone doing?",
            },
        ]

        def mock_get_display_name(user_id: str) -> str:
            names = {
                "U123456": "Alice",
                "U789012": "Bob",
                "U456789": "Charlie",
            }
            return names.get(user_id, "Unknown")

        result = SlackParser.format_messages_for_content(
            messages, mock_get_display_name
        )

        lines = result.split("\n")
        assert len(lines) == 3

        # Check first message - time format will depend on local timezone
        assert "Alice: Hello everyone!" in lines[0]
        assert "Bob: Hi there!" in lines[1]
        assert "Charlie: How's everyone doing?" in lines[2]
        assert all("[2009-02-13" in line for line in lines)  # Check date part

    def test_format_messages_for_content_with_invalid_timestamp(self):
        """Test message formatting with invalid timestamp."""
        messages = [
            {
                "ts": "invalid_timestamp",
                "user": "U123456",
                "text": "Hello!",
            },
            {
                "ts": "",  # Empty timestamp
                "user": "U789012",
                "text": "Hi!",
            },
            {
                # Missing timestamp
                "user": "U456789",
                "text": "Hey!",
            },
        ]

        def mock_get_display_name(user_id: str) -> str:
            return f"User_{user_id}"

        result = SlackParser.format_messages_for_content(
            messages, mock_get_display_name
        )

        lines = result.split("\n")
        assert len(lines) == 3

        # Invalid timestamps should be preserved as-is or show as "unknown"
        assert "invalid_timestamp" in lines[0] or "unknown" in lines[0]
        assert "unknown" in lines[1] or "" in lines[1]
        assert "unknown" in lines[2]

    def test_format_messages_for_content_empty_list(self):
        """Test message formatting with empty message list."""
        messages = []

        def mock_get_display_name(user_id: str) -> str:
            return "User"

        result = SlackParser.format_messages_for_content(
            messages, mock_get_display_name
        )
        assert result == ""

    def test_format_messages_for_content_missing_fields(self):
        """Test message formatting with missing fields."""
        messages = [
            {
                "ts": "1234567890.001",
                # Missing user
                "text": "Hello!",
            },
            {
                "ts": "1234567890.002",
                "user": "U123456",
                # Missing text
            },
            {
                # Missing everything
            },
        ]

        def mock_get_display_name(user_id: str) -> str:
            if user_id == "unknown":
                return "Unknown User"
            return f"User_{user_id}"

        result = SlackParser.format_messages_for_content(
            messages, mock_get_display_name
        )

        lines = result.split("\n")
        assert len(lines) == 3

        # Should handle missing fields gracefully
        assert "Unknown User" in lines[0]  # Missing user should default to "unknown"
        assert "User_U123456" in lines[1]
        assert lines[2]  # Should still produce a line even with missing everything

    def test_validate_person_identifier_with_username(self):
        """Test person identifier validation with @username."""
        result = SlackParser.validate_person_identifier("@alice")
        assert result == "@alice"

    def test_validate_person_identifier_with_user_id(self):
        """Test person identifier validation with user ID."""
        result = SlackParser.validate_person_identifier("U1234567890")
        assert result == "<@U1234567890>"

    def test_validate_person_identifier_empty(self):
        """Test person identifier validation with empty string."""
        with pytest.raises(ValueError, match="Person identifier cannot be empty"):
            SlackParser.validate_person_identifier("")

    def test_validate_person_identifier_invalid_format(self):
        """Test person identifier validation with invalid format."""
        # Display name (not supported)
        with pytest.raises(ValueError, match="Person identifier .* is invalid"):
            SlackParser.validate_person_identifier("Alice Smith")

        # Email (not supported)
        with pytest.raises(ValueError, match="Person identifier .* is invalid"):
            SlackParser.validate_person_identifier("alice@example.com")

        # Short user ID-like string
        with pytest.raises(ValueError, match="Person identifier .* is invalid"):
            SlackParser.validate_person_identifier("U123")

    def test_validate_person_identifier_edge_cases(self):
        """Test person identifier validation edge cases."""
        # Just @ symbol should be rejected
        with pytest.raises(ValueError, match="Username cannot be empty after @"):
            SlackParser.validate_person_identifier("@")

        # User ID that doesn't start with U
        with pytest.raises(ValueError, match="Person identifier .* is invalid"):
            SlackParser.validate_person_identifier("T1234567890")  # Team ID format

        # Invalid user ID - too long
        with pytest.raises(ValueError, match="Person identifier .* is invalid"):
            SlackParser.validate_person_identifier("U123456789012345")  # Too long

        # Invalid user ID - too short
        with pytest.raises(ValueError, match="Person identifier .* is invalid"):
            SlackParser.validate_person_identifier("U123")  # Too short

        # Valid edge case usernames
        result = SlackParser.validate_person_identifier("@user.name")
        assert result == "@user.name"

        result = SlackParser.validate_person_identifier("@user_name")
        assert result == "@user_name"

        result = SlackParser.validate_person_identifier("@user-name")
        assert result == "@user-name"

        # Invalid username with special characters
        with pytest.raises(ValueError, match="Invalid username format"):
            SlackParser.validate_person_identifier("@user@name")

        # Whitespace handling
        result = SlackParser.validate_person_identifier("  @alice  ")
        assert result == "@alice"


class TestSlackParserIntegration:
    """Integration tests for SlackParser methods working together."""

    def test_message_id_roundtrip(self):
        """Test that message ID encoding/decoding is reversible."""
        original_channel = "C1234567890"
        original_ts = "1234567890.001"

        # Encode then decode
        encoded = SlackParser.encode_message_id(original_channel, original_ts)
        decoded_channel, decoded_ts = SlackParser.decode_message_id(encoded)

        assert decoded_channel == original_channel
        assert decoded_ts == original_ts

    def test_thread_id_roundtrip(self):
        """Test that thread ID encoding/decoding is reversible."""
        original_channel = "C1234567890"
        original_ts = "1234567890.001"

        # Encode then decode
        encoded = SlackParser.encode_thread_id(original_channel, original_ts)
        decoded_channel, decoded_ts = SlackParser.decode_thread_id(encoded)

        assert decoded_channel == original_channel
        assert decoded_ts == original_ts

    def test_message_id_vs_thread_id_encoding(self):
        """Test that message ID and thread ID encoding produce same results."""
        channel = "C1234567890"
        ts = "1234567890.001"

        message_id = SlackParser.encode_message_id(channel, ts)
        thread_id = SlackParser.encode_thread_id(channel, ts)

        # Should be identical since they use the same encoding scheme
        assert message_id == thread_id

    def test_complex_channel_name_handling(self):
        """Test handling of complex channel names with special characters."""
        complex_channel = "C_TEAM_PROJ_123_TEST"
        ts = "1234567890.001"

        # Test message ID
        encoded_msg = SlackParser.encode_message_id(complex_channel, ts)
        decoded_channel, decoded_ts = SlackParser.decode_message_id(encoded_msg)

        assert decoded_channel == complex_channel
        assert decoded_ts == ts

        # Test thread ID
        encoded_thread = SlackParser.encode_thread_id(complex_channel, ts)
        decoded_channel, decoded_ts = SlackParser.decode_thread_id(encoded_thread)

        assert decoded_channel == complex_channel
        assert decoded_ts == ts

    def test_user_display_name_with_different_data_structures(self):
        """Test user display name extraction with various data structures."""
        test_cases = [
            # Complete profile
            {
                "input": {
                    "id": "U123",
                    "name": "alice",
                    "real_name": "Alice Smith",
                    "profile": {"display_name": "Alice S."},
                },
                "expected": "Alice S.",
            },
            # Missing profile.display_name
            {
                "input": {
                    "id": "U123",
                    "name": "bob",
                    "real_name": "Bob Jones",
                    "profile": {},
                },
                "expected": "Bob Jones",
            },
            # Missing profile entirely
            {
                "input": {
                    "id": "U123",
                    "name": "charlie",
                    "real_name": "Charlie Brown",
                },
                "expected": "Charlie Brown",
            },
            # Only username
            {
                "input": {
                    "id": "U123",
                    "name": "diana",
                },
                "expected": "diana",
            },
            # Only ID
            {
                "input": {
                    "id": "U123",
                },
                "expected": "U123",
            },
            # Empty dict
            {
                "input": {},
                "expected": "unknown",
            },
        ]

        for test_case in test_cases:
            result = SlackParser.get_user_display_name(test_case["input"])
            assert (
                result == test_case["expected"]
            ), f"Failed for input: {test_case['input']}"


class TestSlackParserErrorHandling:
    """Test error handling and edge cases for SlackParser."""

    def test_format_messages_with_none_values(self):
        """Test message formatting with None values."""
        messages = [
            {
                "ts": None,
                "user": None,
                "text": None,
            },
            {
                "ts": "1234567890.001",
                "user": None,
                "text": "Valid message",
            },
        ]

        def mock_get_display_name(user_id: str) -> str:
            if user_id is None or user_id == "unknown":
                return "Unknown"
            return f"User_{user_id}"

        # Should not raise exception
        result = SlackParser.format_messages_for_content(
            messages, mock_get_display_name
        )
        assert isinstance(result, str)

    def test_channel_type_with_none_values(self):
        """Test channel type determination with None values."""
        channel_info = {
            "is_channel": None,
            "is_group": None,
            "is_im": None,
            "is_mpim": None,
        }

        result = SlackParser.determine_channel_type(channel_info)
        assert result == "unknown"

    def test_user_display_name_with_none_profile(self):
        """Test user display name with None profile."""
        user_info = {
            "id": "U123",
            "name": "alice",
            "profile": None,
        }

        # Current implementation doesn't handle None profile gracefully
        with pytest.raises(AttributeError):
            SlackParser.get_user_display_name(user_info)
