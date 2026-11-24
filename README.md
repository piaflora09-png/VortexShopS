# VORTEX HACKBOT

Vortex is an integrated Discord community, verification, security, moderation, and reporting platform built with Python, discord.py, aiohttp, and PostgreSQL.

## Features

- Discord OAuth2 login with state/CSRF protection and guild membership verification
- Verified-role assignment and verification records
- Encrypted 8-hour web sessions and logout
- Staff-only moderation slash commands for warning, timeout, kick, and ban
- Transparent message-flood, mention-spam, and join-raid detection
- Private support-ticket channel creation
- PostgreSQL-backed moderation, security, key, subscription, ticket, campaign, giveaway, middleman, transaction, and audit schemas
- Responsive neon dashboard and health endpoint
- Non-destructive authorized campaign and giveaway helpers
- Transaction reports distinguish recorded activity from the configured $50,000 daily target

## Local setup

1. Install Python 3.11+ and PostgreSQL.
2. Create a virtual environment:
   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill every required Discord and database value.
   Generate a strong `SESSION_SECRET` with one of these commands:
   ```powershell
   py -3.11 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   This is a server-side cookie-session secret, not a Discord or database password. Generate a different value for local and production; keep it unchanged so existing sessions remain valid. `SESSION_SECRET` must contain at least 32 characters.
4. In the Discord Developer Portal, add `http://localhost:8080/auth/callback` as an OAuth2 redirect.
5. Create the Verified role and copy its ID. Add a log channel and at least one staff role.
6. Start the application:
   ```powershell
   python app.py
   ```
7. Open `http://localhost:8080`.

## Discord permissions

OAuth requests only `identify` and `guilds`. The bot requires:

- View Channels
- Send Messages
- Manage Roles (to assign/remove the Verified role)
- Moderate Members (timeouts)
- Kick Members
- Ban Members
- Manage Channels (tickets)
- Read Message History

Administrator permission is not required; prefer setting only the permissions above and placing the bot role above managed roles.

## Render deployment

1. Push the project to a repository.
2. Create a Blueprint using `render.yaml`.
3. Provision the generated PostgreSQL database.
4. Set the redirect, public URL, Guild ID, role IDs, channel ID, bot token, OAuth credentials, and staff-role list.
5. Add the exact Render callback URL to Discord OAuth2 redirects.
6. Deploy and verify `/health`.

## API authorization

Web actions require a valid cookie session. Administrative POST actions also require the matching `X-CSRF-Token`. Admin identity is checked against owner status and configured staff Discord roles/administrator permissions. API keys are never served to frontend JavaScript.

## Security boundaries

- The project does not collect IP addresses.
- The project does not implement malware, RAT functionality, arbitrary shell execution, credential access, or persistence.
- Campaign delivery is restricted to explicitly selected configured Discord channels and includes an inter-message delay.
- Giveaways use cryptographically secure random selection and record entries in PostgreSQL.
- The `$50,000` value is a target, never an inferred or fabricated transaction total.
- OAuth state is one-time, stored in PostgreSQL, and expires after ten minutes.

## Testing status

The project includes syntax and import validation commands below. Live Discord and PostgreSQL behavior require credentials and a running database. Do not report live tests as successful unless both services were available during the test.

```powershell
python -m compileall -q .
python -c "import app, bot, database, config, security, verification, moderation"
```

## Current implementation scope

This deliverable is an integrated working core. It provides the authenticated dashboard, PostgreSQL initialization, OAuth verification, moderation slash commands, security-event logging, private support-ticket creation, and reusable campaign, giveaway, middleman, and transaction helpers. Full UI/API CRUD screens for access keys, subscriptions, campaign scheduling, giveaway buttons, ticket transcripts/reopening/assignment, middleman disputes/vouches, CSV export, AI endpoints, and monthly staff reports remain follow-up work. Those database structures and module boundaries are included so the follow-up work can be connected without a redesign.
