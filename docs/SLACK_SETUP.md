# Slack API Integration Setup

This guide explains how to set up the Slack API integration for the Google API Integration App.

## Prerequisites

1. A Slack workspace where you have admin permissions
2. Python environment with the required dependencies installed

## Step 1: Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App"
3. Choose "From scratch"
4. Enter an app name (e.g., "Praga Core Integration")
5. Select your workspace
6. Click "Create App"

## Step 2: Configure OAuth Scopes

In your app's settings, go to "OAuth & Permissions" and add these Bot Token Scopes:

### Required Scopes:
- `channels:history` - View messages in public channels
- `channels:read` - View basic information about public channels
- `groups:history` - View messages in private channels
- `groups:read` - View basic information about private channels
- `im:history` - View messages in direct messages
- `im:read` - View basic information about direct messages
- `mpim:history` - View messages in group direct messages
- `mpim:read` - View basic information about group direct messages
- `users:read` - View people in a workspace

## Step 3: Install App to Workspace

1. In "OAuth & Permissions", click "Install to Workspace"
2. Review the permissions and click "Allow"
3. Copy the "Bot User OAuth Token" (starts with `xoxb-`)

## Step 4: Create Credentials File

Create a credentials file with your app's client ID and secret:

1. In your Slack app settings, go to "Basic Information"
2. Copy the "Client ID" and "Client Secret" 
3. Create the file `~/.praga/secrets/slack_credentials.json`:

```json
{
  "client_id": "your-client-id-here",
  "client_secret": "your-client-secret-here"
}
```

**Important**: Keep this file secure and never commit it to version control!

## Step 5: Test the Integration

Run the app - it will automatically start the OAuth2 flow if no valid token exists:

```bash
python app.py
```

**First Run**: The app will:
1. Display an authorization URL
2. Open your browser to authorize the app
3. Ask you to paste the redirect URL
4. Save the token for future use

**Subsequent Runs**: The app will use the saved token automatically.

Example queries:
- "Search conversations in channel general"
- "Find recent conversations from the last 3 days"  
- "Search for threads containing 'meeting'"
- "Get conversation chunk C1234567890(0)"

## API Usage Notes

### Channel IDs
- Channel IDs start with 'C' (e.g., 'C1234567890')
- DM IDs start with 'D' (e.g., 'D1234567890')
- Group DM IDs start with 'G' (e.g., 'G1234567890')

### Conversation Chunking
- Messages are automatically chunked by temporal proximity (1-hour windows by default)
- Each chunk has a unique ID in format: `{channel_id}({chunk_index})`
- Chunks are linked with next/previous relationships

### Thread Handling
- Threads are identified by their `thread_ts` timestamp
- Thread data is cached after first access
- Only the parent message content is indexed for search

### Authentication
- Uses OAuth2 flow with proper state management
- Tokens are stored securely in `~/.praga/secrets/`
- Automatic token refresh when needed
- No need to manually manage tokens

### Caching
- All conversation and thread data is cached in memory
- No cache invalidation - data persists for the session
- Re-running the app will start with a fresh cache

## Troubleshooting

### Common Issues:

1. **"missing_scope" error**: Make sure all required scopes are added to your app
2. **"channel_not_found" error**: Verify the channel ID is correct and the bot has access
3. **"not_in_channel" error**: Invite the bot to private channels before accessing them
4. **OAuth errors**: Ensure the credentials file exists and contains valid client_id/client_secret
5. **"invalid_auth" error**: Delete the token files in `~/.praga/secrets/` to restart OAuth flow

### Getting Channel IDs:
- Right-click on a channel in Slack → "Copy link"
- The ID is in the URL: `/archives/C1234567890/`
- Or use the Slack API: `conversations.list`

## Security Notes

- Store your credentials file securely and never commit it to version control
- OAuth2 tokens are stored in `~/.praga/secrets/` with proper permissions
- The app can only access channels you've authorized during OAuth flow
- Private channels require explicit invitation of the app
- DMs require the user to have started a conversation with the app
- Tokens are automatically refreshed when needed 