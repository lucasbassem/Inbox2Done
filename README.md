# Inbox2Done
Inbox2Done is an email productivity assistant that summarizes messages, identifies priorities and deadlines, recommends next steps, and generates suggested replies, with planned Gmail and Outlook integration.
## Features

- Summarizes long or complicated emails
- Assigns High, Medium, or Low priority
- Detects deadlines and important dates
- Recommends next actions
- Generates suggested email replies
- Categorizes emails by type
- Supports a clean web-based interface
- Planned Gmail integration
- Planned Outlook integration

## Planned Email Integrations

Inbox2Done is being designed to work with:

- Gmail through the Gmail API and Google OAuth
- Outlook and Microsoft 365 through Microsoft Graph and OAuth

Users will explicitly authorize read-only access to their own email accounts.

The first integration will focus on securely retrieving recent emails and creating a daily summary. Sending emails or modifying mailbox data will not be enabled by default.

## How It Works

1. The user provides email content or connects an approved email account.
2. Inbox2Done analyzes the email.
3. The application returns:
   - A concise summary
   - Priority level
   - Email category
   - Recommended actions
   - Detected deadlines
   - A suggested reply

## Technology Stack

### Frontend

- React
- TypeScript
- Vite
- Mantine
- Tabler Icons

### Backend

- Bun
- Express
- TypeScript
- OpenAI API

### Planned Integrations

- Gmail API
- Google OAuth 2.0
- Microsoft Graph API
- Microsoft OAuth 2.0

## Project Structure
inbox2done/
├── client/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── types/
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── package.json
├── server/
│   ├── src/
│   │   ├── routes/
│   │   ├── services/
│   │   ├── utils/
│   │   ├── types/
│   │   └── index.ts
│   ├── .env.example
│   └── package.json
├── .gitignore
└── README.md
