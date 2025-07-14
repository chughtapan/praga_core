import base64
import logging
import re
from html import unescape
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class GmailParser:
    """Parser for Gmail messages that handles both HTML and text content.

    This class provides methods to:
    - Decode base64 encoded email content
    - Clean and normalize text content
    - Convert HTML to plain text
    - Handle email-specific formatting (quotes, forwards, etc.)
    """

    # Common patterns for detecting email reply sections
    REPLY_PATTERNS = [
        # Gmail style: Handles optional name/email more simply, DOTALL flag
        r"(?im)(?:^|\n)\s*On\s+[A-Za-z]{3},\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4}(?:\s+at\s+\d{1,2}:\d{2}\s+(?:AM|PM))?\s*.*?\s*(?:wrote|writes):",
        # Simple date format
        r"(?m)(?:^|\n)\s*On\s+\d{1,2}/\d{1,2}/\d{2,4}\s+[^\n]+\s+(?:wrote|writes):",
        # Traditional email format - Reintroduced
        r"(?m)(?:^|\n)\s*From:\s*[\w\s<>@\.\-]+(?:\\[mailto:[\w@\.\-]+\\])?",
        # Outlook style headers (allowing newlines between fields)
        r"(?m)(?:^|\n)\s*From:.*?\n+\s*Sent:.*?\n+\s*To:.*?\n+\s*Subject:.*",
    ]

    # Index of the 'From:' pattern in REPLY_PATTERNS. Used for special handling
    # to prevent it from matching inside forwarded message headers.
    FROM_PATTERN_INDEX = 2

    # Patterns for detecting forwarded messages
    FORWARD_MARKERS = [r"-+ Forwarded message -+", r"Begin forwarded message:"]

    # Fields commonly found in forwarded message headers
    FORWARD_FIELDS = [r"^From:", r"^Date:", r"^Subject:", r"^To:", r"^Cc:"]

    @staticmethod
    def decode_body(body_data: str) -> str:
        """Decode base64 encoded email body.

        Args:
            body_data: Base64 encoded string

        Returns:
            Decoded string, or empty string if decoding fails
        """
        try:
            # Add padding if needed
            padding = 4 - (len(body_data) % 4)
            if padding != 4:
                body_data += "=" * padding
            return base64.urlsafe_b64decode(body_data.encode("ASCII")).decode("utf-8")
        except Exception as e:
            logger.error("Failed to decode email body: %s", e)
            return ""

    @staticmethod
    def clean_special_chars(text: str) -> str:
        """Clean up special characters and normalize whitespace.

        Handles various Unicode spaces, invisible characters, and normalizes
        multiple spaces/newlines into a consistent format.

        Args:
            text: Input text to clean

        Returns:
            Cleaned text with normalized whitespace
        """
        if not text:
            return ""

        # Map of special characters to their replacements
        special_chars = {
            "\u202f": " ",  # narrow no-break space
            "\u200b": "",  # zero-width space
            "\u200c": "",  # zero-width non-joiner
            "\u200d": "",  # zero-width joiner
            "\u200e": "",  # left-to-right mark
            "\u200f": "",  # right-to-left mark
            "\u00a0": " ",  # non-breaking space
            "\ufeff": "",  # zero-width no-break space
            "\u2800": "",  # braille pattern blank
            "\u2007": " ",  # figure space
            "\u2028": "\n",  # line separator
            "\u2029": "\n",  # paragraph separator
            "\u00ad": "",  # soft hyphen
            "\u034f": "",  # combining grapheme joiner
        }

        # Replace special characters
        for char, replacement in special_chars.items():
            text = text.replace(char, replacement)

        # Normalize whitespace
        text = re.sub(r"[ \t]+", " ", text)  # Multiple spaces/tabs to single space
        text = re.sub(r"\n\s+\n", "\n\n", text)  # Remove spaces between blank lines
        return text.strip()

    @staticmethod
    def _remove_html_elements(soup: BeautifulSoup) -> None:
        """Remove unwanted HTML elements from BeautifulSoup object.

        Removes script, style, metadata, and hidden elements.

        Args:
            soup: BeautifulSoup object to modify
        """
        # Remove script, style, and hidden elements
        for element in soup(
            ["script", "style", "head", "title", "meta", '[style*="display: none"]']
        ):
            element.decompose()

        # Remove Gmail quote sections
        for element in soup.find_all(class_="gmail_quote"):
            element.decompose()

    @staticmethod
    def _is_reply_quote(text: str) -> bool:
        """Check if text matches common email reply patterns.

        Args:
            text: Text to check

        Returns:
            True if text appears to be a reply quote
        """
        # Check against the currently defined REPLY_PATTERNS
        return any(
            re.search(pattern, text, re.MULTILINE | re.DOTALL)
            for pattern in GmailParser.REPLY_PATTERNS
        )

    @staticmethod
    def html_to_text(html_content: str) -> str:
        """Convert HTML content to plain text while preserving structure.

        Handles:
        - HTML entity unescaping
        - Removal of scripts, styles, and hidden elements
        - Removal of email reply quotes
        - Special character normalization

        Args:
            html_content: HTML string to convert

        Returns:
            Plain text version of the HTML content
        """
        if not html_content:
            return ""

        try:
            html_content = unescape(html_content)
            html_content = GmailParser.clean_special_chars(html_content)

            # Parse HTML
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove unwanted elements
            GmailParser._remove_html_elements(soup)

            # Handle blockquotes that look like reply sections
            for quote in soup.find_all("blockquote"):
                if GmailParser._is_reply_quote(quote.get_text()):
                    quote.decompose()

            # Extract text
            text = soup.get_text(separator="\n", strip=True)

            # If no text was extracted but there was input, return the cleaned input
            if not text and html_content.strip():
                return GmailParser.clean_special_chars(html_content.strip())

            return GmailParser.clean_special_chars(text)

        except Exception as e:
            logger.error("Failed to convert HTML to text: %s", e)
            # For invalid HTML, return the cleaned original content
            return GmailParser.clean_special_chars(html_content.strip())

    @classmethod
    def _process_message_part(cls, part: Dict[str, Any]) -> Optional[str]:
        """Process a single message part and extract its content.

        Handles different MIME types appropriately:
        - text/plain: Clean and return as is
        - text/html: Convert to plain text
        - multipart/*: Process recursively

        Args:
            part: Gmail API message part

        Returns:
            Extracted and cleaned text content, or None if no content found
        """
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        body_data = body.get("data", "")

        if mime_type == "text/plain" and body_data:
            return cls.decode_body(body_data)
        elif mime_type == "text/html" and body_data:
            return cls.html_to_text(cls.decode_body(body_data))
        elif mime_type.startswith("multipart/"):
            # Process nested parts
            parts = part.get("parts", [])
            contents = []
            for nested_part in parts:
                content = cls._process_message_part(nested_part)
                if content:
                    contents.append(content)
            return "\n".join(contents) if contents else None

        return None

    @classmethod
    def extract_body(cls, payload: Dict[str, Any]) -> str:
        """Extract and clean the body content from a Gmail message payload.

        Handles nested MIME structures and selects the most appropriate content
        type (preferring plain text over HTML when both are available).

        Args:
            payload: Gmail API message payload

        Returns:
            Cleaned email body text
        """
        content = cls._process_message_part(payload)
        if content:
            return cls.clean_message_content(content)
        return ""

    @classmethod
    def _find_earliest_valid_reply_index(
        cls, text: str, earliest_forward_marker_index: int
    ) -> int:
        """Find the earliest reply marker that appears before any forward markers.

        This prevents cutting off legitimate "From:" headers within forwarded
        messages by ensuring we only match reply markers that appear before
        any forwarded content.

        Args:
            text: Email text to search
            earliest_forward_marker_index: Index of earliest forward marker

        Returns:
            Index of earliest valid reply marker, or -1 if none found
        """
        earliest_reply_index = len(text)

        for i, pattern in enumerate(cls.REPLY_PATTERNS):
            match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
            if match:
                match_start = match.start()
                # Special handling for the "From:" pattern
                if i == cls.FROM_PATTERN_INDEX and earliest_forward_marker_index != -1:
                    # Only consider this match if it's before any forward markers
                    if match_start < earliest_forward_marker_index:
                        earliest_reply_index = min(earliest_reply_index, match_start)
                else:
                    earliest_reply_index = min(earliest_reply_index, match_start)

        return earliest_reply_index if earliest_reply_index < len(text) else -1

    @classmethod
    def clean_message_content(cls, text_content: str) -> str:
        """Clean email content by removing reply chains and forwarded messages.

        Uses pattern matching to identify and remove:
        - Email reply chains (On [date] ... wrote:)
        - Forwarded message content
        - Headers and metadata from forwarded/replied messages

        Args:
            text_content: Raw email text content

        Returns:
            Cleaned email content with only the primary message
        """
        if not text_content:
            return ""

        # Find forward markers first
        earliest_forward_marker_index = -1
        for marker in cls.FORWARD_MARKERS:
            match = re.search(marker, text_content, re.IGNORECASE | re.MULTILINE)
            if match:
                start_index = match.start()
                if earliest_forward_marker_index == -1:
                    earliest_forward_marker_index = start_index
                else:
                    earliest_forward_marker_index = min(
                        earliest_forward_marker_index, start_index
                    )

        # Find the earliest reply index that doesn't conflict with forwards
        earliest_reply_index = cls._find_earliest_valid_reply_index(
            text_content, earliest_forward_marker_index
        )

        # Determine the cutoff point
        cutoff_index = len(text_content)
        if earliest_reply_index != -1:
            cutoff_index = min(cutoff_index, earliest_reply_index)
        if earliest_forward_marker_index != -1:
            cutoff_index = min(cutoff_index, earliest_forward_marker_index)

        # Extract the main content
        main_content = (
            text_content[:cutoff_index]
            if cutoff_index != len(text_content)
            else text_content
        )

        # Process line by line for final cleanup
        lines = main_content.split("\n")
        filtered_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                filtered_lines.append("")
                continue

            # Skip lines that look like forwarded message fields
            if any(
                re.match(field, line, re.IGNORECASE) for field in cls.FORWARD_FIELDS
            ):
                continue

            filtered_lines.append(line)

        return cls._process_final_lines(filtered_lines)

    @classmethod
    def _process_final_lines(cls, lines: List[str]) -> str:
        """Process the final list of lines and return clean content.

        Args:
            lines: List of content lines

        Returns:
            Final cleaned content string
        """
        # Remove trailing empty lines
        while lines and not lines[-1]:
            lines.pop()

        # Rejoin and do final cleaning
        result = "\n".join(lines)
        result = cls.clean_special_chars(result)

        # Remove excessive blank lines (more than 2 consecutive)
        result = re.sub(r"\n{3,}", "\n\n", result)

        return result.strip()

    @classmethod
    def parse_message(cls, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Gmail message data into a normalized format.

        This method was used in the original GmailService to parse messages.
        It extracts headers, body content, and other metadata.

        Args:
            message_data: Raw Gmail API message data

        Returns:
            Normalized message data dictionary with keys:
            - thread_id: Thread ID
            - subject: Email subject
            - sender: Sender email address
            - recipients: List of recipient email addresses
            - cc: List of CC email addresses
            - body: Cleaned email body text
            - time: Email timestamp
            - permalink: Gmail web URL for the message
        """
        from datetime import datetime
        from email.utils import parsedate_to_datetime

        # Extract headers
        headers = message_data.get("payload", {}).get("headers", [])
        header_dict = {header["name"]: header["value"] for header in headers}

        # Parse basic fields
        thread_id = message_data.get("threadId", "")
        subject = header_dict.get("Subject", "")
        sender = header_dict.get("From", "")

        # Parse recipients
        recipients = []
        to_header = header_dict.get("To", "")
        if to_header:
            # Simple email extraction - split by comma and clean
            recipients = [r.strip() for r in to_header.split(",") if r.strip()]

        # Parse CC recipients
        cc = []
        cc_header = header_dict.get("Cc", "")
        if cc_header:
            cc = [c.strip() for c in cc_header.split(",") if c.strip()]

        # Parse timestamp
        date_str = header_dict.get("Date", "")
        time = datetime.now()
        if date_str:
            try:
                time = parsedate_to_datetime(date_str)
            except (ValueError, TypeError):
                pass

        # Extract body using existing method
        payload = message_data.get("payload", {})
        body = cls.extract_body(payload)

        # Create permalink
        message_id = message_data.get("id", "")
        permalink = f"https://mail.google.com/mail/u/0/#inbox/{message_id}"

        return {
            "thread_id": thread_id,
            "subject": subject,
            "sender": sender,
            "recipients": recipients,
            "cc": cc,
            "body": body,
            "time": time,
            "permalink": permalink,
        }

    @classmethod
    def parse_thread(cls, thread_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Gmail thread data into a normalized format.

        Args:
            thread_data: Raw Gmail API thread data

        Returns:
            Normalized thread data dictionary with keys:
            - id: Thread ID
            - subject: Thread subject (from first message)
            - messages: List of message summaries
            - permalink: Gmail web URL for the thread
        """
        messages = thread_data.get("messages", [])
        if not messages:
            return {
                "id": thread_data.get("id", ""),
                "subject": "",
                "messages": [],
                "permalink": "",
            }

        # Use first message for thread subject
        first_message = messages[0]
        first_parsed = cls.parse_message(first_message)

        # Parse all messages in thread
        message_summaries = []
        for msg in messages:
            parsed = cls.parse_message(msg)
            message_summaries.append(
                {
                    "id": msg.get("id", ""),
                    "sender": parsed["sender"],
                    "recipients": parsed["recipients"],
                    "cc": parsed.get("cc", []),
                    "body": parsed["body"],
                    "time": parsed["time"],
                }
            )

        thread_id = thread_data.get("id", "")
        thread_permalink = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"

        return {
            "id": thread_id,
            "subject": first_parsed["subject"],
            "messages": message_summaries,
            "permalink": thread_permalink,
        }

    @classmethod
    def build_message(
        cls,
        to: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a message for sending via Gmail API.

        Args:
            to: List of recipient email addresses
            subject: Email subject
            body: Email body text
            cc: Optional CC recipients
            bcc: Optional BCC recipients
            thread_id: Optional thread ID for replies

        Returns:
            Message dict ready for Gmail API
        """
        import base64
        from email.message import EmailMessage

        # Create message
        message = EmailMessage()
        message["To"] = ", ".join(to)
        message["Subject"] = subject

        if cc:
            message["Cc"] = ", ".join(cc)
        if bcc:
            message["Bcc"] = ", ".join(bcc)

        message.set_content(body)

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        # Prepare request body
        send_body = {"raw": raw_message}
        if thread_id:
            send_body["threadId"] = thread_id

        return send_body

    @classmethod
    def build_reply_message(
        cls, original_message: Dict[str, Any], reply_body: str, reply_all: bool = False
    ) -> Dict[str, Any]:
        """Build a reply message.

        Args:
            original_message: Original message data from Gmail API
            reply_body: Reply body text
            reply_all: Whether to reply to all recipients

        Returns:
            Reply message dict ready for Gmail API
        """
        import base64
        from email.message import EmailMessage

        # Extract recipients from original
        headers = original_message.get("payload", {}).get("headers", [])
        header_dict = {header["name"]: header["value"] for header in headers}

        # Reply to sender
        reply_to = [header_dict.get("From", "")]

        # Add CC if reply all
        cc = []
        if reply_all and header_dict.get("Cc"):
            cc = [email.strip() for email in header_dict["Cc"].split(",")]

        # Build subject
        original_subject = header_dict.get("Subject", "")
        if not original_subject.startswith("Re:"):
            subject = f"Re: {original_subject}"
        else:
            subject = original_subject

        # Create reply message
        message = EmailMessage()
        message["To"] = ", ".join(reply_to)
        message["Subject"] = subject

        if cc:
            message["Cc"] = ", ".join(cc)

        # Add threading headers
        if header_dict.get("Message-ID"):
            message["In-Reply-To"] = header_dict["Message-ID"]
            message["References"] = header_dict["Message-ID"]

        message.set_content(reply_body)

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        return {"raw": raw_message, "threadId": original_message.get("threadId", "")}
