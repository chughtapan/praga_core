# Microsoft Outlook OAuth Setup Guide

This guide walks you through setting up Microsoft OAuth 2.0 authentication for the PragaWeb application to access Microsoft Graph APIs (Outlook, Calendar, Contacts, OneDrive).

## Prerequisites

- A Microsoft account (personal) or Azure Active Directory account (work/school)
- Access to the Azure Portal or Microsoft App Registration Portal
- PragaWeb application already set up

## Step 1: Register Your Application

### Option A: Azure Portal (Recommended)

1. Go to the [Azure Portal](https://portal.azure.com/)
2. Search for and select "Azure Active Directory"
3. In the left sidebar, click "App registrations"
4. Click "New registration"

### Option B: Microsoft App Registration Portal

1. Go to the [Microsoft App Registration Portal](https://apps.dev.microsoft.com/)
2. Sign in with your Microsoft account
3. Click "Add an app"

## Step 2: Configure Application Registration

**Application Details:**
- Name: `PragaWeb`
- Supported account types: "Accounts in any organizational directory and personal Microsoft accounts"
- Redirect URI: 
  - Type: "Public client/native (mobile & desktop)"
  - URI: `http://localhost`

Click "Register" to create the application.

## Step 3: Configure API Permissions

1. In your app registration, go to "API permissions"
2. Click "Add a permission"
3. Select "Microsoft Graph"
4. Choose "Delegated permissions"
5. Add the following permissions:

### Required Permissions:
- **Mail.Read** - Read user mail
- **Mail.ReadWrite** - Read and write access to user mail
- **Mail.Send** - Send mail as a user
- **Calendars.Read** - Read user calendars
- **Calendars.ReadWrite** - Read and write user calendars
- **Contacts.Read** - Read user contacts
- **Contacts.ReadWrite** - Read and write user contacts
- **Files.Read** - Read user files
- **Files.ReadWrite** - Read and write user files
- **User.Read** - Read user profile
- **offline_access** - Maintain access to data you have given it access to

6. Click "Add permissions"
7. Click "Grant admin consent" (if you have admin rights) or ask your admin to grant consent

## Step 4: Configure Authentication

1. Go to "Authentication" in your app registration
2. Under "Advanced settings", ensure the following are configured:
   - **Allow public client flows**: Yes
   - **Supported account types**: Personal Microsoft accounts and work/school accounts

3. Under "Redirect URIs", ensure you have:
   - Type: "Public client/native (mobile & desktop)"
   - URI: `http://localhost`

## Step 5: Get Application Credentials

1. Go to "Overview" in your app registration
2. Copy the **Application (client) ID** - you'll need this

**Note**: For desktop applications using MSAL, you only need the client ID. Client secrets are not required or recommended for public client applications.

## Step 6: Configure PragaWeb

### Option A: Using Environment Variables

Set the following environment variable:

```bash
export MICROSOFT_CLIENT_ID="your_application_id_here"
```

### Option B: Using .env File

Create a `.env` file in your project root:

```bash
# .env file
MICROSOFT_CLIENT_ID=your_application_id_here
```

## Troubleshooting

### Common Issues

**"AADSTS65001: The user or administrator has not consented":**
- Ensure admin consent has been granted for the required permissions
- Try the authentication flow again

**"AADSTS50011: The redirect URI specified in the request does not match":**
- Verify the redirect URI in your app registration is: `http://localhost`
- Check for trailing slashes or case sensitivity

**"invalid_client" error:**
- Verify your client ID is correct
- Ensure you're using the correct Application (client) ID from Azure Portal

**"insufficient_scope" error:**
- Ensure all required permissions are granted
- Re-authenticate to get tokens with the new scopes

### Permission Issues

**"Forbidden" when accessing APIs:**
- Check that the user has consented to the required permissions
- Verify the permissions are configured correctly in the app registration
- Ensure the user's account type is supported

**"Token has expired" error:**
- MSAL automatically handles token refresh
- If issues persist, clear the MSAL cache and re-authenticate

## API Limits and Throttling

Be aware of Microsoft Graph API limits:

- **Outlook Mail**: 10,000 requests per 10 minutes per user
- **Calendar**: 10,000 requests per 10 minutes per user
- **Contacts**: 10,000 requests per 10 minutes per user
- **OneDrive**: Varies by operation type

Microsoft Graph implements throttling and will return HTTP 429 responses when limits are exceeded.

## Monitoring and Analytics

Monitor your application's usage:

1. Go to Azure Portal > Azure Active Directory > App registrations
2. Select your app > "Usage & insights"
3. View sign-in logs and API usage statistics
4. Set up alerts for unusual activity

## Additional Resources

- [Microsoft Graph Documentation](https://docs.microsoft.com/en-us/graph/)
- [Azure Active Directory Documentation](https://docs.microsoft.com/en-us/azure/active-directory/)
- [Microsoft Graph API Reference](https://docs.microsoft.com/en-us/graph/api/overview)
- [OAuth 2.0 on Microsoft Identity Platform](https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow)
- [Microsoft Graph Permissions Reference](https://docs.microsoft.com/en-us/graph/permissions-reference)

## Support and Community

- [Microsoft Graph Support](https://docs.microsoft.com/en-us/graph/support)
- [Stack Overflow - Microsoft Graph](https://stackoverflow.com/questions/tagged/microsoft-graph)
- [Microsoft Tech Community](https://techcommunity.microsoft.com/t5/microsoft-graph/ct-p/MicrosoftGraph)
