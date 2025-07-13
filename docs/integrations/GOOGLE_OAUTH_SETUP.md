# Google OAuth Setup Guide

This guide walks you through setting up Google OAuth 2.0 authentication for the PragaWeb application to access Google APIs (Gmail, Calendar, Contacts, Docs, Drive).

## Prerequisites

- A Google account
- Access to the Google Cloud Console
- PragaWeb application already set up

## Step 1: Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click "Select a project" dropdown at the top
3. Click "New Project"
4. Enter a project name (e.g., "PragaWeb Integration")
5. Select your organization (if applicable)
6. Click "Create"

## Step 2: Enable Required APIs

1. In the Google Cloud Console, ensure your new project is selected
2. Go to "APIs & Services" > "Library"
3. Search for and enable the following APIs:
   - **Gmail API** - For email access
   - **Google Calendar API** - For calendar access
   - **People API** - For contacts access
   - **Google Docs API** - For document access
   - **Google Drive API** - For file access

For each API:
1. Click on the API name
2. Click "Enable"
3. Wait for the API to be enabled

## Step 3: Configure OAuth Consent Screen

1. Go to "APIs & Services" > "OAuth consent screen"
2. Choose "External" (unless you have a Google Workspace account)
3. Click "Create"

### Fill out the OAuth consent screen:

**App Information:**
- App name: `PragaWeb`
- User support email: Your email address
- App logo: (Optional) Upload a logo
- App domain: Leave blank for development
- Authorized domains: Leave blank for development
- Developer contact information: Your email address

**Scopes:**
Click "Add or Remove Scopes" and add the following scopes:
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.compose`
- `https://www.googleapis.com/auth/calendar.readonly`
- `https://www.googleapis.com/auth/contacts.readonly`
- `https://www.googleapis.com/auth/directory.readonly`
- `https://www.googleapis.com/auth/documents.readonly`
- `https://www.googleapis.com/auth/drive.readonly`

**Test Users (for External apps):**
Add your email address as a test user so you can test the integration.

4. Click "Save and Continue" through all steps

## Step 4: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. Select "Desktop application" as the application type
4. Name it "PragaWeb Desktop Client"
5. Click "Create"

## Step 5: Download Credentials

1. After creating the OAuth client, click the download icon next to your client ID
2. Save the JSON file as `client_secret.json` in a secure location
3. **Important**: Never commit this file to version control

## Step 6: Configure PragaWeb

### Option A: Using Environment Variables

Set the following environment variables:

```bash
export GOOGLE_CLIENT_ID="your_client_id_here"
export GOOGLE_CLIENT_SECRET="your_client_secret_here"
```

### Option B: Using Secrets Manager

Add the credentials to your secrets manager:

```python
# Using PragaWeb's secrets manager
from pragweb.secrets_manager import get_secrets_manager

secrets_manager = get_secrets_manager()
secrets_manager.set_secret("google_client_id", "your_client_id_here")
secrets_manager.set_secret("google_client_secret", "your_client_secret_here")
```

### Option C: Using credentials.json file

Place your `client_secret.json` file in the project root and rename it to `google_credentials.json`.

## Step 7: Test the Integration

1. Start your PragaWeb application
2. The application will automatically detect the need for authentication
3. A browser window will open asking you to sign in to Google
4. Grant the requested permissions
5. The application will receive an authorization code and exchange it for tokens

## Step 8: Verify Access

After authentication, you can verify the integration is working by:

1. Checking that email search works
2. Verifying calendar events can be retrieved
3. Confirming contacts are accessible
4. Testing document access

## Troubleshooting

### Common Issues

**"This app isn't verified" warning:**
- Click "Advanced" then "Go to [App Name] (unsafe)" during development
- For production, you'll need to go through Google's verification process

**"Access blocked" error:**
- Ensure you've added your email as a test user in the OAuth consent screen
- Check that all required APIs are enabled

**"Invalid client" error:**
- Verify your client ID and secret are correct
- Ensure the OAuth client type is set to "Desktop application"

**Token refresh issues:**
- Delete any existing token files and re-authenticate
- Check that the `offline_access` scope is included

### Error Messages

**"The redirect URI in the request does not match":**
- The redirect URI should be `http://localhost:8080` for desktop applications
- If you need a different port, update it in the OAuth client configuration

**"insufficient_scope" error:**
- Ensure all required scopes are configured in the OAuth consent screen
- Re-authenticate to get tokens with the new scopes

## Security Best Practices

1. **Never commit credentials to version control**
2. **Use environment variables or secure secret storage**
3. **Regularly rotate client secrets**
4. **Monitor API usage in Google Cloud Console**
5. **Implement proper token refresh logic**
6. **Use the principle of least privilege for scopes**

## Production Deployment

For production deployment:

1. **Verify your app** through Google's verification process
2. **Use a proper domain** instead of localhost
3. **Implement proper error handling** for authentication failures
4. **Set up monitoring** for API quota usage
5. **Configure proper backup** for refresh tokens

## API Quotas and Limits

Be aware of Google API quotas:

- **Gmail API**: 1 billion quota units per day
- **Calendar API**: 1 million requests per day
- **People API**: 300 requests per minute per user
- **Drive API**: 20,000 requests per 100 seconds per user

Monitor your usage in the Google Cloud Console under "APIs & Services" > "Quotas".

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Gmail API Documentation](https://developers.google.com/gmail/api)
- [Google Calendar API Documentation](https://developers.google.com/calendar)
- [People API Documentation](https://developers.google.com/people)
- [Google Drive API Documentation](https://developers.google.com/drive)