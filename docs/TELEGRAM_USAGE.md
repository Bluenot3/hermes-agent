# Telegram Bot Usage Guide

Use the Hermes Agent Telegram bot to control your projects, run commands, review code, and interact with the AI agent — all from your phone.

## Prerequisites

- A Telegram account
- A bot token from [@BotFather](https://t.me/BotFather)
- A deployed instance of this gateway (Railway, Docker, or local)

See [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md) for deployment instructions.

---

## Command Reference

### General

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and show the welcome message |
| `/help` | Show the full command list |
| `/status` | Check bot and agent connectivity |
| `/cancel` | Clear your session history and reset the loaded project |

### Project Commands

| Command | Description |
|---------|-------------|
| `/load <project>` | Load a project context (e.g. `/load my-webapp`) |
| `/code <path>` | Ask the agent to review a file or directory |
| `/test` | Run the test suite for the loaded project |

### Execution Commands *(require approval)*

| Command | Description |
|---------|-------------|
| `/exec <cmd>` | Execute a shell command (shows approval buttons) |
| `/deploy <env>` | Deploy to an environment — e.g. `/deploy staging` |

### Admin Commands *(admin user only)*

| Command | Description |
|---------|-------------|
| `/admin_panel` | Show admin dashboard |
| `/logs [N]` | Show the last N lines of the agent log (default: 20) |
| `/stats` | Show usage statistics |

---

## Workflow Examples

### Load a Project and Run Tests

```
/load my-webapp
/test
```

The bot will acknowledge the loaded project and then run the test suite, streaming results back.

### Review a File from Your Phone

```
/code src/api/auth.py
```

The agent analyses the file at that path and returns a code review.

### Execute a Command with Approval

```
/exec npm run build
```

The bot presents **✅ Confirm** and **❌ Cancel** inline buttons.  
Tap **Confirm** to run the command; the output streams back to you.

### Deploy to Staging

```
/deploy staging
```

Same approval flow as `/exec`.  After confirmation the agent runs the deployment pipeline.

### Free-Form Chat

You can also just send any plain message:

```
What tests are failing?
Why is the build slow?
Summarise the recent commits.
```

The agent uses your loaded project context when answering.

### File Upload for Code Review

Send a file directly in the chat (tap the paperclip icon on mobile).  
Optionally add a caption with instructions, for example:

```
[attach auth.py]
Caption: Check for security issues
```

---

## Approval Buttons

Commands that execute code or trigger deployments require explicit confirmation:

```
⚠️ Execute command:
   npm run build

Do you want to proceed?
  [✅ Confirm]  [❌ Cancel]
```

Tap **Confirm** to proceed or **Cancel** to abort.  
Pending approvals expire when you start a new session (`/cancel`).

---

## Session Memory

Each user has their own session.  The bot remembers:

- **Loaded project** — set with `/load`, reset with `/cancel`
- **Conversation history** — accumulated across messages until reset

The session is stored in a local SQLite database and persists between bot restarts.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Token from @BotFather |
| `TELEGRAM_ADMIN_USER_ID` | Recommended | Your numeric Telegram user ID |
| `OPENROUTER_API_KEY` | ✅ | OpenRouter key for model access |
| `TELEGRAM_ALLOWED_USERS` | — | Comma-separated additional user IDs |
| `GATEWAY_ALLOW_ALL_USERS` | — | Set to `true` for a fully public bot |
| `TELEGRAM_WEBHOOK_URL` | — | Enables webhook mode (e.g. Railway URL) |
| `TELEGRAM_WEBHOOK_SECRET` | Recommended | Random secret for webhook security |
| `TELEGRAM_RATE_LIMIT_PER_MINUTE` | — | Messages/min per user (default: 30) |
| `HERMES_DEFAULT_MODEL` | — | Override the default AI model |

See [`.env.telegram.example`](../.env.telegram.example) for the full list.

---

## Troubleshooting

### Bot does not respond

1. Check that `TELEGRAM_BOT_TOKEN` is set correctly (format: `123456:ABC…`).
2. Check Railway / Docker logs for errors.
3. If using webhooks, verify with:
   ```bash
   curl https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo
   ```

### "Not authorised" error

Your Telegram user ID is not in `TELEGRAM_ALLOWED_USERS` (or `TELEGRAM_ADMIN_USER_ID`).  
Get your ID from [@userinfobot](https://t.me/userinfobot) and set the variable.

### Agent returns "not available"

Check that `OPENROUTER_API_KEY` is set and valid.

### Webhook not receiving updates

- Ensure the URL is publicly reachable (Railway deployed and running).
- Re-register the webhook:
  ```bash
  bash scripts/telegram_deploy.sh
  ```

---

## Security Notes

- **Never commit** your real bot token or `.env` file to version control.
- Set `TELEGRAM_WEBHOOK_SECRET` in production to prevent spoofed requests.
- Restrict access with `TELEGRAM_ADMIN_USER_ID` and `TELEGRAM_ALLOWED_USERS`.
- Dangerous commands (`/exec`, `/deploy`) always require an inline approval button tap.
- All command invocations are logged for audit purposes.
