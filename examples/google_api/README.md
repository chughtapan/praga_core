# Google API Integration App

A comprehensive integration app that provides unified access to Google APIs (Gmail, Calendar, People, Google Docs) and Slack APIs through a clean, extensible architecture.

## Features

### Google APIs
- **Gmail**: Search and retrieve emails with full content
- **Calendar**: Access calendar events and schedules  
- **People/Contacts**: Search and manage contacts
- **Google Docs**: Search, chunk, and retrieve document content

### Slack APIs  
- **Conversations**: Temporally-chunked message history from channels/DMs
- **Threads**: Complete thread content and metadata
- **Search**: Content-based search across conversations and threads

### Architecture
- **Clean 3-layer design**: Pages (data models) → Services (API logic) → Toolkits (search tools)
- **Unified authentication**: OAuth2 flows for both Google and Slack
- **Smart caching**: SQLModel-based caching with auto-ingestion
- **Intelligent chunking**: Chonkie-powered content chunking for large documents/conversations

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Authentication

#### Google APIs
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the required APIs:
   - Gmail API
   - Calendar API
   - People API
   - Google Docs API
   - Google Drive API
4. Create OAuth2 credentials (Desktop application)
5. Download the credentials file as `~/.praga/secrets/google_credentials.json`

#### Slack APIs
1. Go to [Slack API Apps](https://api.slack.com/apps)
2. Create a new app "From scratch"
3. Add the required OAuth scopes (see [SLACK_SETUP.md](SLACK_SETUP.md))
4. Create `~/.praga/secrets/slack_credentials.json`:
   ```json
   {
     "client_id": "your-client-id",
     "client_secret": "your-client-secret"
   }
   ```

### 3. Test Authentication

```bash
cd auth
python test_auth.py
```

This will test both Google and Slack authentication flows.

### 4. Run the App

```bash
python app.py
```

On first run, both services will guide you through their respective OAuth2 flows.

## Usage Examples

### Email Search
- "Find emails from john@example.com from last week"
- "Search for emails containing 'project update'"
- "Get recent unread emails"

### Calendar Search  
- "Show my meetings for today"
- "Find calendar events with 'standup' in the title"
- "Get events between 2024-01-01 and 2024-01-31"

### Document Search
- "Search for Google Docs containing 'quarterly report'"
- "Find recent documents updated in the last 7 days"
- "Get document titled 'Meeting Notes'"

### Slack Search
- "Search conversations in channel general"
- "Find recent conversations from the last 3 days"
- "Search for threads containing 'deployment'"

## Architecture Details

### Authentication (`auth/`)
- **Singleton pattern**: Single instance per service across the app
- **OAuth2 flows**: Proper state management and token storage
- **Automatic refresh**: Tokens refreshed automatically when needed
- **Secure storage**: Credentials stored in `~/.praga/secrets/`

### Pages (`pages/`)
Data models representing different content types:
- `EmailPage`, `CalendarEventPage`, `PersonPage` (Google)
- `GDocHeader`, `GDocChunk` (Google Docs)
- `SlackThread`, `SlackConversation` (Slack)

### Services (`services/`)
Business logic and API interactions:
- Handle authentication and API calls
- Register page handlers with context
- Provide search methods for toolkits
- Implement caching and chunking logic

### Toolkits (`toolkits/`)
Search and retrieval tools:
- Extend `RetrieverToolkit` with proper tool registration
- Return `PaginatedResponse` objects
- Provide user-friendly search interfaces

## Configuration

### File Locations
- Credentials: `~/.praga/secrets/`
- Google: `google_credentials.json`, `google_token.pickle`  
- Slack: `slack_credentials.json`, `slack_token.json`

### Scopes

#### Google Scopes
- `gmail.readonly` - Read Gmail messages
- `calendar.readonly` - Read calendar events
- `contacts.readonly` - Read contacts
- `documents.readonly` - Read Google Docs
- `drive.readonly` - List Drive files

#### Slack Scopes  
- `channels:read`, `channels:history` - Public channels
- `groups:read`, `groups:history` - Private channels
- `im:read`, `im:history` - Direct messages
- `mpim:read`, `mpim:history` - Group DMs
- `users:read` - User information

## Development

### Adding New APIs
1. Create page models in `pages/`
2. Implement service in `services/` with page handlers
3. Create toolkit in `toolkits/` with search tools
4. Register service and toolkit in `app.py`

### Extending Authentication
- Add new authenticator to `auth/` package
- Follow singleton pattern like existing authenticators
- Update `auth/__init__.py` to export new authenticator

## Troubleshooting

### Common Issues
1. **Missing credentials**: Ensure credential files exist in `~/.praga/secrets/`
2. **OAuth errors**: Delete token files to restart OAuth flow
3. **API errors**: Check that required APIs are enabled in respective consoles
4. **Permission errors**: Ensure proper scopes are configured

### Debug Mode
Set logging level to DEBUG for detailed output:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Security

- **Never commit credentials** to version control
- **Secure token storage** in user's home directory
- **Proper OAuth2 flows** with state management
- **Minimal required scopes** for each service
- **Automatic token refresh** prevents stale credentials

## Contributing

1. Follow the established architecture patterns
2. Add proper error handling and logging
3. Include docstrings for all public methods
4. Test authentication flows thoroughly
5. Update documentation for new features 