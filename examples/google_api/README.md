# Google API Toolkits

This directory contains two powerful toolkits for integrating with Google APIs: **GmailToolkit** and **CalendarToolkit**. These toolkits are built on top of the `praga_core.retriever_toolkit` framework and provide easy-to-use interfaces for retrieving emails and calendar events.

## Features

### Gmail Toolkit Features
- Search emails by sender, recipient, CC participants
- Search emails by date range
- Search emails by keywords in body/subject
- Get recent emails and unread emails
- Extract email content from various formats (plain text, HTML)

### Calendar Toolkit Features
- Get calendar events by date range
- Search events by attendee or organizer
- Search events by topic/keywords
- Get today's events, upcoming events, and weekly meetings
- Support for multiple calendars

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Google OAuth Credentials

#### Step 1: Create a Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Gmail API and Google Calendar API:
   - Go to "APIs & Services" > "Library"
   - Search for "Gmail API" and enable it
   - Search for "Google Calendar API" and enable it

#### Step 2: Create OAuth 2.0 Credentials
1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth 2.0 Client IDs"
3. Choose "Desktop application" as the application type
4. Download the credentials JSON file

#### Step 3: Save Credentials
Save the downloaded credentials file as `~/.praga_secrets/credentials.json`

```bash
mkdir -p ~/.praga_secrets
cp /path/to/your/downloaded/credentials.json ~/.praga_secrets/credentials.json
```

## Quick Start

### Gmail Toolkit Example

```python
from gmail_toolkit import GmailToolkit

# Initialize the toolkit
gmail = GmailToolkit()

# Get emails from a specific sender
emails = gmail.get_emails_by_sender("example@email.com", max_results=10)

# Search emails by keyword
meeting_emails = gmail.get_emails_with_body_keyword("meeting")

# Get emails from date range
emails = gmail.get_emails_by_date_range("2024-01-01", "2024-01-31")

# Get recent emails (stateless tool)
recent = gmail.get_recent_emails(days=7)

# Pagination example
paginated_result = gmail.get_emails_by_sender("sender@email.com", page=0)
print(f"Found {len(paginated_result.documents)} emails on page 0")
print(f"Has next page: {paginated_result.metadata.has_next_page}")
```

### Calendar Toolkit Example

```python
from calendar_toolkit import CalendarToolkit

# Initialize the toolkit
calendar = CalendarToolkit()

# Get events for date range
events = calendar.get_calendar_entries_by_date_range("2024-06-01", "2024-06-30")

# Get events by attendee
events = calendar.get_calendar_entries_by_attendee("attendee@email.com")

# Search events by topic
events = calendar.get_calendar_entries_by_topic("sprint planning")

# Get today's events (stateless tool)
today_events = calendar.get_todays_events()

# Get upcoming events
upcoming = calendar.get_upcoming_events(days=14)
```

## Document Structure

Both toolkits return `Document` objects with the following structure:

### Email Document
```python
Document(
    id="email_message_id",
    content="Subject: ...\nFrom: ...\nDate: ...\n\nEmail body content...",
    metadata={
        'subject': 'Email Subject',
        'from': 'sender@email.com',
        'to': 'recipient@email.com',
        'cc': 'cc@email.com',
        'date': 'Mon, 1 Jan 2024 12:00:00 +0000',
        'message_id': 'gmail_message_id',
        'token_count': 150,
        'labels': ['INBOX', 'UNREAD']
    }
)
```

### Calendar Document
```python
Document(
    id="calendar_event_id",
    content="Title: Meeting\nStart: 2024-01-01T10:00:00Z\nEnd: 2024-01-01T11:00:00Z\n...",
    metadata={
        'summary': 'Meeting Title',
        'description': 'Meeting description',
        'start_time': '2024-01-01T10:00:00Z',
        'end_time': '2024-01-01T11:00:00Z',
        'location': 'Conference Room A',
        'organizer_email': 'organizer@email.com',
        'organizer_name': 'John Doe',
        'attendee_emails': ['attendee1@email.com', 'attendee2@email.com'],
        'attendee_names': ['Jane Smith', 'Bob Johnson'],
        'event_id': 'calendar_event_id',
        'token_count': 75,
        'status': 'confirmed',
        'created': '2024-01-01T09:00:00Z',
        'updated': '2024-01-01T09:30:00Z'
    }
)
```

## Advanced Features

### Caching
All tools support caching with configurable TTL:
- Gmail tools: 15-minute cache TTL
- Calendar tools: 15-minute cache TTL
- Stateless tools: Custom TTL (1 hour for recent emails, 30 minutes for unread emails, etc.)

