# Testing Guide for Smithery Deployment

This guide helps you test your Praga MCP server setup before deploying to Smithery.

## Prerequisites

- Python 3.11+
- Docker (for container testing)
- Google Cloud account (for OAuth setup)
- OpenAI API key

## Quick Test

Run the automated test script:

```bash
python test_smithery_setup.py
```

This script will:
- Verify all required files exist
- Validate smithery.yaml configuration
- Check Docker availability
- Test environment variable setup
- Create test configuration files

## Testing Steps

### 1. Environment Variable Testing

#### Option A: Using .env file
```bash
# Copy the test template
cp .env.test .env

# Edit .env with your actual credentials
# Required: OPENAI_API_KEY
# Optional: GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, GOOGLE_OAUTH_REFRESH_TOKEN

# Test the server
python -m pragweb.mcp_server
```

#### Option B: Export variables directly
```bash
export OPENAI_API_KEY='sk-your-openai-key'
export GOOGLE_OAUTH_CLIENT_ID='your-client-id.apps.googleusercontent.com'
export GOOGLE_OAUTH_CLIENT_SECRET='your-client-secret'
export GOOGLE_OAUTH_REFRESH_TOKEN='your-refresh-token'

python -m pragweb.mcp_server
```

### 2. Obtaining Google OAuth Credentials

#### Step 1: Create OAuth Client
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable APIs:
   - Gmail API
   - Google Calendar API
   - Google Drive API
   - Google Docs API
   - People API
4. Go to "APIs & Services" > "Credentials"
5. Click "Create Credentials" > "OAuth client ID"
6. Choose "Desktop app" as the application type
7. Save the client ID and secret

#### Step 2: Get Refresh Token
```bash
# Run the helper script
python scripts/get_google_refresh_token.py

# Or provide credentials as arguments
python scripts/get_google_refresh_token.py "YOUR_CLIENT_ID" "YOUR_CLIENT_SECRET"
```

The script will:
- Open a browser for authorization
- Request access to required Google services
- Display your refresh token
- Optionally save credentials to .env.google

### 3. Docker Testing

#### Build the image
```bash
docker build -t praga-mcp-test .
```

#### Run with minimal config (OpenAI only)
```bash
docker run -it \
  -e OPENAI_API_KEY='sk-your-key' \
  -e PYTHONUNBUFFERED=1 \
  praga-mcp-test
```

#### Run with full Google integration
```bash
docker run -it \
  -e OPENAI_API_KEY='sk-your-key' \
  -e GOOGLE_OAUTH_CLIENT_ID='your-client-id' \
  -e GOOGLE_OAUTH_CLIENT_SECRET='your-client-secret' \
  -e GOOGLE_OAUTH_REFRESH_TOKEN='your-refresh-token' \
  -e PYTHONUNBUFFERED=1 \
  praga-mcp-test
```

### 4. Testing MCP Protocol

Once the server is running, you can test it with an MCP client:

#### Using fastmcp CLI (if installed)
```bash
# List available tools
fastmcp tools list

# Test search functionality
fastmcp tools call search_pages '{"instruction": "find recent emails"}'

# Test get_pages
fastmcp tools call get_pages '{"page_uris": ["gmail:email:123"]}'
```

## Troubleshooting

### Common Issues

1. **"OPENAI_API_KEY environment variable is required"**
   - Set the OPENAI_API_KEY environment variable
   - Check your .env file is in the correct location

2. **"Docker daemon not running"**
   - Start Docker Desktop or Docker service
   - Verify with: `docker --version`

3. **"Failed to refresh token from environment variables"**
   - Verify your Google OAuth credentials are correct
   - Check the refresh token hasn't expired
   - Try generating a new refresh token

4. **"Failed to import MCP server"**
   - Install dependencies: `pip install -e .`
   - Ensure you're in the project root directory
   - Check Python version is 3.11+

### Authentication Priority

The server tries authentication in this order:
1. Environment variables (GOOGLE_OAUTH_*)
2. Stored credentials in secrets database
3. Interactive OAuth flow (local only)

For Smithery deployment, use option 1 (environment variables).

## Verification Checklist

Before deploying to Smithery:

- [ ] `smithery.yaml` exists and is valid
- [ ] `Dockerfile` builds successfully
- [ ] `.dockerignore` excludes unnecessary files
- [ ] Google auth supports environment variables
- [ ] MCP server starts without errors
- [ ] OpenAI API key is available
- [ ] (Optional) Google OAuth credentials obtained
- [ ] (Optional) Docker image tested locally

## Next Steps

Once testing is complete:

1. Commit all changes:
   ```bash
   git add smithery.yaml Dockerfile .dockerignore
   git add src/pragweb/google_api/auth.py
   git commit -m "Add Smithery deployment configuration with OAuth support"
   git push origin main
   ```

2. Deploy on Smithery:
   - Go to https://smithery.ai
   - Connect your GitHub repository
   - Configure environment variables
   - Deploy!

For detailed deployment instructions, see [SMITHERY_DEPLOYMENT.md](SMITHERY_DEPLOYMENT.md).