# Google API Handler Architecture Example

This directory demonstrates the new **Handler-Based Architecture** for integrating with Google APIs. This architecture provides a clean separation where:

- **Handlers** do complete work: take minimal input (like email_id), make all API calls, parse data, and return full documents
- **ServerContext** manages handlers and provides a centralized registry
- **Toolkits** become simple: they just collect IDs and ask the context to create pages

## Architecture Overview

### Key Components

1. **ServerContext**: Central registry that manages page handlers and caching
2. **Handlers**: Complete functions that take minimal input and return full documents  
3. **Page Classes**: Structured document classes (EmailDocument, CalendarEventDocument)
4. **Simplified Toolkits**: Just collect IDs and delegate to context

### Handler Registration Patterns

```python
from praga_core.context import ServerContext

ctx = ServerContext()

# Pattern 1: Decorator (FastAPI-style)
@ctx.handler(EmailDocument)
def handle_email(email_id: str) -> EmailDocument:
    # Make Gmail API calls, parse email, return complete document
    return EmailDocument(...)

# Pattern 2: Programmatic registration  
ctx.register_handler(create_email_document, EmailDocument)
```

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

### Complete Handler Example

```python
from praga_core.context import ServerContext
from handlers.email_handlers import EmailDocument, create_email_document
from handlers.calendar_handlers import CalendarEventDocument, create_calendar_document

# Create context and register handlers
ctx = ServerContext()

# Register handlers using decorator pattern
@ctx.handler(EmailDocument)
def handle_email_complete(email_id: str) -> EmailDocument:
    """Complete email handler - does Gmail API calls and parsing."""
    return create_email_document(email_id)

@ctx.handler(CalendarEventDocument)  
def handle_calendar_complete(event_id: str, calendar_id: str = "primary") -> CalendarEventDocument:
    """Complete calendar handler - does Calendar API calls and parsing."""
    return create_calendar_document(event_id, calendar_id)

# Now you can create pages with just IDs
email_doc = ctx.create_page(EmailDocument, "email_123")
event_doc = ctx.create_page(CalendarEventDocument, "event_456")
```

### Simplified Toolkit Example

```python
class SimplifiedGmailToolkit:
    def __init__(self, context: ServerContext):
        self.context = context
        # Set up Gmail API service here
    
    def get_recent_emails(self, count: int = 5) -> list[EmailDocument]:
        """Get recent emails - just collect IDs and delegate to context."""
        # 1. Use Gmail API to search for recent message IDs
        message_ids = self._search_recent_message_ids(count)
        
        # 2. For each ID, ask context to create the page
        emails = []
        for email_id in message_ids:
            email = self.context.create_page(EmailDocument, email_id)
            emails.append(email)
        
        return emails
    
    def _search_recent_message_ids(self, count: int) -> list[str]:
        # Gmail API logic to get message IDs only
        # Much simpler than before!
        pass
```

## Document Structure  

The new architecture returns structured page objects:

### EmailDocument
```python
@dataclass
class EmailDocument(Page):
    id: str
    subject: str
    sender: str
    recipient: str
    cc: str
    time: str
    body: str
    html_body: str
    labels: list[str]
    message_id: str
    thread_id: str
```

### CalendarEventDocument
```python
@dataclass  
class CalendarEventDocument(Page):
    id: str
    summary: str
    description: str
    start_time: str
    end_time: str
    location: str
    organizer_email: str
    organizer_name: str
    attendee_emails: list[str]
    attendee_names: list[str]
    status: str
```

## Architecture Benefits

✅ **Complete Handlers**: Each handler does ALL the work from ID to final document  
✅ **Clean Separation**: Toolkits find IDs, handlers create documents, context coordinates  
✅ **Easy Testing**: Test handlers independently with mock IDs  
✅ **FastAPI-style DX**: Familiar decorator patterns for registration  
✅ **Automatic Caching**: Context automatically caches created pages  
✅ **No Circular Dependencies**: Clear dependency flow  

## Running the Examples

### Complete Handler Demo
```bash
python complete_handler_demo.py
```
Shows both registration patterns and simplified toolkit examples.

### Integration Example  
```bash
python integration_example.py
```
Shows a realistic example with actual Gmail/Calendar integration.

## File Structure

```
examples/google_api/
├── handlers/           # Complete handler implementations
│   ├── email_handlers.py      # Gmail API → EmailDocument
│   └── calendar_handlers.py   # Calendar API → CalendarEventDocument
├── pages/             # Document class definitions  
│   ├── email_pages.py         # EmailDocument class
│   └── calendar_pages.py      # CalendarEventDocument class
├── toolkits/          # Simplified toolkits (just ID collection)
│   ├── gmail_toolkit.py       # Gmail ID search + context delegation
│   └── calendar_toolkit.py    # Calendar ID search + context delegation
├── complete_handler_demo.py   # Architecture demonstration
├── integration_example.py     # Realistic usage example
└── auth.py           # Google OAuth helper
```

