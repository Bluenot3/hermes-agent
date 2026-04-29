# 📱 Telegram Bot Setup - Complete Guide

## Overview

Your Hermes Agent Telegram bot lets you:
- ✅ Control your projects from your phone
- ✅ Execute commands with approval
- ✅ Review code on the go
- ✅ Deploy to staging/production
- ✅ Run tests and monitor logs
- ✅ Everything 24/7 from cloud

**Total setup time: 5 minutes**

---

## Option 1: Automatic Setup (Recommended)

### Step 1: Run Setup Wizard
```bash
cd ~/path/to/hermes-agent
python src/gateway/telegram_setup.py
```

This interactive wizard will:
1. Guide you through creating a Telegram bot
2. Collect your bot token
3. Get your user ID
4. Set API keys
5. Configure Railway automatically
6. Deploy everything

### Step 2: Follow Prompts
The wizard asks for:
- **Bot Token** (from BotFather)
- **User ID** (from @userinfobot)
- **API Key** (from openrouter.ai)
- **Webhook URL** (auto-filled)

### Step 3: Done!
```
✓ Setup Complete!
✓ Configuration saved
✓ Ready to deploy
```

---

## Option 2: Manual Setup (If Wizard Doesn't Work)

### Step 1: Create Bot Token (2 min)

**On your phone:**
```
1. Open Telegram
2. Search for: BotFather
3. Send: /newbot
4. Name: My Hermes Agent
5. Username: my_hermes_agent_bot  ← MUST end with "bot"
6. Copy the token → 123456789:ABCDEFGHIjklmnop...
```

**Alternative:**
- Search: `t.me/BotFather`
- `/token` → Select your bot

### Step 2: Get Your User ID (1 min)

**On your phone:**
```
1. Open Telegram
2. Search for: @userinfobot
3. Send: /start
4. Copy your ID → 123456789
```

### Step 3: Create .env.telegram File

```bash
cat > .env.telegram << 'EOF'
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIjklmnopqrstuvwxyz_EXAMPLE
TELEGRAM_ADMIN_USER_ID=123456789
TELEGRAM_WEBHOOK_URL=https://hermes-telegram-production.up.railway.app/telegram/webhook
OPENROUTER_API_KEY=sk-or-v1-your-api-key-here
EOF
```

### Step 4: Deploy to Railway

```bash
# Login to Railway
railway login

# Create project
railway init

# Set variables from .env.telegram
railway variables set --file .env.telegram

# Push to deploy
git push origin main

# Wait for deployment (2-3 minutes)
railway logs
```

### Step 5: Verify Deployment

```bash
# Check if bot is running
railway logs | grep "telegram"

# Should see: "Telegram webhook registered successfully"
```

### Step 6: Set Webhook

```bash
# After Railway deployment is complete:
TOKEN="your_bot_token_here"
URL="https://hermes-telegram-production.up.railway.app"

curl -X POST \
  "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${URL}/telegram/webhook\"}"

# Should return: {"ok":true,"result":true}
```

### Step 7: Test

**On Telegram:**
```
1. Search for your bot: @my_hermes_agent_bot
2. Send: /help
3. Bot should respond with command list
```

---

## Environment Variables Explained

| Variable | Example | Purpose |
|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | Your bot's secret token (from BotFather) |
| `TELEGRAM_ADMIN_USER_ID` | `123456789` | Your Telegram user ID (for access control) |
| `TELEGRAM_WEBHOOK_URL` | `https://app.railway.app/telegram/webhook` | Where Telegram sends messages |
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | Free/paid model access |

---

## Bot Commands

### Basic Commands
```
/help          Show all commands
/status        Check bot status
/cancel        Cancel current task
```

### Project Commands
```
/load my-app              Load project context
/code src/main.py         Review code file
/test                     Run tests
/exec npm run build       Execute command (needs approval)
/git status               Check git status
/deploy staging           Deploy (needs approval)
```

### Admin Commands
```
/admin_panel    Show admin dashboard
/logs [N]       Show last N log lines
/stats          Show usage statistics
```

---

## Examples

### Load a Project and Run Tests

```
You: /load my-webapp

Bot: ✓ Loaded Project
     Project: my-webapp
     Branch: main
     Status: Ready

You: /test

Bot: 🧪 Running Tests
     Running: pytest src/tests/ -v
     ...
     ✓ 45 passed
     ⏱️ 3.2s
```

### Review Code from Phone

```
You: /code src/api/auth.py

Bot: 📝 Code Review: src/api/auth.py
     
     Issues Found:
     • Unused import: os
     • Missing type hints on line 12
     • Function too long (89 lines)
     
     Suggestions:
     ✓ Use pathlib instead of os.path
     ✓ Add docstring to main()
     ✓ Break into smaller functions
```

### Deploy with Approval

```
You: /deploy production

Bot: ⚠️ Deploy to production?
     [✓ Confirm] [✗ Cancel]

You: [Tap Confirm]

Bot: 🚀 Deploying to production...
     Building...
     Testing...
     Deploying...
     ✓ Live in 2 minutes!
```

### Free-Form Chat

```
You: What tests are failing?

Bot: Running tests...
     ✓ 45 passed
     ✗ 3 failed:
     - test_auth_logout.py:12
     - test_payment.py:45
     - test_api_validation.py:78
```

---

## Troubleshooting

### Bot doesn't respond
```bash
# Check Railway logs
railway logs

# Look for errors, check bot token format
# Token should be: numbers:letters (123456:ABC...)
```

### "Invalid token" error
```
✓ Correct:   123456789:ABCDEFGHIjklmnopqrstuvwxyz_EXAMPLE
✗ Wrong:     My-Bot (name doesn't work)
✗ Wrong:     Just the ID number
```

### Can't find bot on Telegram
```bash
# Make sure username ends with "bot"
✓ my_hermes_agent_bot
✗ my_hermes_agent

# Search by username
t.me/my_hermes_agent_bot
```

### Webhook not connecting
```bash
# Check if Railway is deployed
railway status

# Verify webhook URL is correct
TOKEN="your_token"
curl "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"

# Should show your webhook URL and "pending_update_count": 0
```

### Bot runs locally but not on Railway
```
Common cause: Missing environment variables on Railway

Solution:
railway variables set TELEGRAM_BOT_TOKEN=your_token
railway variables set TELEGRAM_ADMIN_USER_ID=your_id
railway redeploy
```

---

## Security Notes

- ✅ **Never commit** `.env.telegram` or bot token to git
- ✅ **Keep token secret** - only share bot username, not token
- ✅ **Commands need approval** - dangerous commands require button confirmation
- ✅ **Admin only** - only your user ID can execute commands
- ✅ **Audit logging** - all commands logged for security
- ✅ **Rate limiting** - 30 messages/min to prevent abuse

---

## Cost Breakdown

| Component | Cost |
|-----------|------|
| Railway hosting | $5/month (first $5 free) |
| OpenRouter models | $0 (free tier) |
| Telegram bot | $0 (completely free) |
| **Total** | **$0-5/month** |

---

## Next Steps

1. ✅ **Run setup wizard** (or manual setup)
2. ✅ **Deploy to Railway**
3. ✅ **Test on Telegram**
4. ✅ **Load your project**
5. ✅ **Start working from phone!**

---

## Quick Checklist

- [ ] Created bot with BotFather
- [ ] Copied bot token
- [ ] Got user ID from @userinfobot
- [ ] Set environment variables on Railway
- [ ] Deployed to Railway (`git push origin main`)
- [ ] Set webhook via curl
- [ ] Found bot on Telegram (`@your_bot_name`)
- [ ] Sent `/help` - got response
- [ ] Sent `/status` - got response
- [ ] Loaded project with `/load`
- [ ] Executed command

**Once all checked ✓ - You're ready!**

---

## Support

Having issues?

1. Check Railway logs: `railway logs`
2. Check bot webhook: `curl https://api.telegram.org/bot{TOKEN}/getWebhookInfo`
3. Review this guide
4. Check Discord: https://discord.gg/NousResearch

---

**Happy bot building! 🤖**
