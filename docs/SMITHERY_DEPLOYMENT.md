# Smithery Deployment Guide

This guide explains how to deploy the Praga Core MCP server on Smithery.

## Prerequisites

1. A GitHub account with this repository
2. A Smithery account (sign up at https://smithery.ai)
3. An OpenAI API key
4. (Optional) Google OAuth credentials for Google API features

## Deployment Steps

### 1. Push to GitHub

Ensure your repository includes the following files:
- `smithery.yaml` - Smithery configuration
- `Dockerfile` - Container build instructions
- `.dockerignore` - Optimize Docker builds

```bash
git add smithery.yaml Dockerfile .dockerignore
git commit -m "Add Smithery deployment configuration"
git push origin main
```

### 2. Connect to Smithery

1. Log in to [Smithery](https://smithery.ai)
2. Click "Deploy a new server" or "Add Server"
3. Connect your GitHub account if not already connected
4. Select this repository from the list

### 3. Configure Deployment

1. Smithery will detect the `smithery.yaml` configuration
2. Review the deployment settings
3. Click "Deploy" to start the deployment process

### 4. Configure Environment

After deployment, users will need to provide:
- **OPENAI_API_KEY** (required): Your OpenAI API key for LLM interactions
- **GOOGLE_OAUTH_CLIENT_ID** (optional): For Google API features
- **GOOGLE_OAUTH_CLIENT_SECRET** (optional): For Google API features
- **GOOGLE_OAUTH_REFRESH_TOKEN** (optional): For automated Google API authentication

### Obtaining Google OAuth Credentials

#### 1. Create OAuth Client ID
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the required APIs (Gmail, Calendar, Drive, Docs, People)
4. Go to "APIs & Services" > "Credentials"
5. Click "Create Credentials" > "OAuth client ID"
6. Choose "Desktop app" as the application type
7. Save the client ID and client secret

#### 2. Obtain Refresh Token
To get a refresh token, you'll need to run the OAuth flow once locally:

```python
# save this as get_refresh_token.py
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/directory.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Create flow with your client ID and secret
flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": "YOUR_CLIENT_ID",
            "client_secret": "YOUR_CLIENT_SECRET",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    scopes=SCOPES
)

# Run the flow
creds = flow.run_local_server(port=0)

print(f"Refresh Token: {creds.refresh_token}")
```

Run this script, authorize in your browser, and copy the refresh token.

## Using Your Deployed Server

Once deployed, your MCP server will be available through:
- Smithery's web interface
- Claude Desktop (with proper MCP configuration)
- Any MCP-compatible client

### Claude Desktop Configuration

To use with Claude Desktop, add to your Claude configuration:

```json
{
  "mcpServers": {
    "praga-core": {
      "url": "https://smithery.ai/api/mcp/your-server-id",
      "apiKey": "your-smithery-api-key"
    }
  }
}
```

## Features Available

Your deployed MCP server provides:
- Document retrieval using LLMRP protocol
- Google API integrations (Calendar, Gmail, Docs, People)
- Reactive agent for intelligent document search
- Action execution framework
- Page caching system

## Troubleshooting

### Build Failures
- Check the Smithery deployment logs
- Ensure all dependencies in `pyproject.toml` are installable
- Verify the Python version (3.11+)

### Runtime Errors
- Verify all required environment variables are set
- Check the server logs in Smithery dashboard
- Ensure API keys have proper permissions

### Local Testing

To test locally before deployment:

```bash
# Build the Docker image
docker build -t praga-mcp-local .

# Run with environment variables
docker run -it \
  -e OPENAI_API_KEY="your-key" \
  -e PYTHONUNBUFFERED=1 \
  praga-mcp-local
```

## Security Notes

- Never commit API keys or secrets to the repository
- Use Smithery's secure environment variable management
- Tokens are passed ephemerally and not stored long-term by Smithery

## Support

For issues specific to:
- Praga Core: Open an issue in this repository
- Smithery platform: Contact Smithery support or check their documentation at https://smithery.ai/docs