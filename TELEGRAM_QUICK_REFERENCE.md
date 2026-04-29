# 🚀 Telegram Bot - Quick Reference

## One-Liner Commands

### Create Bot (On Telegram)
```
Search: BotFather
Send: /newbot
Name: My Hermes Agent
Username: my_hermes_agent_bot
→ Copy TOKEN
```

### Get Your ID (On Telegram)
```
Search: @userinfobot
Send: /start
→ Copy your ID (numbers only)
```

### Deploy to Railway (Computer)
```bash
railway login
railway init
railway variables set TELEGRAM_BOT_TOKEN=your_token_here
railway variables set TELEGRAM_ADMIN_USER_ID=your_id_here
railway variables set OPENROUTER_API_KEY=sk-or-v1-your-key
git push origin main
```

### Set Webhook (Terminal)
```bash
TOKEN="your_token_here"
URL="https://your-railway-url.up.railway.app/telegram/webhook"

curl -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${URL}\"}"
```

### Interactive Setup (Automatic)
```bash
python src/gateway/telegram_setup.py
# Follow prompts - handles everything automatically
```

---

## Environment Variables Needed

```env
TELEGRAM_BOT_TOKEN=123456789:ABCDEFGHIjklmnopqrstuvwxyz_EXAMPLE
TELEGRAM_ADMIN_USER_ID=123456789
OPENROUTER_API_KEY=sk-or-v1-...
```

---

## Test Commands (On Telegram)

```
/help           → Show commands
/status         → Check if bot is alive
/load my-app    → Load Arsenal project
/exec npm test  → Run tests (needs approval)
/code src/app   → Analyze code
/deploy staging → Deploy (needs approval)
/admin_panel    → Admin dashboard
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot doesn't respond | Check Railway logs: `railway logs` |
| Token error | Verify token format has `:` → `123456:ABC` |
| Webhook failed | Check URL is correct and Railway is running |
| Can't find bot | Username must end with `bot` → use `t.me/botname` |
| Wrong environment | Check `railway env` to see all variables |

---

## One Complete Example

```bash
# 1. Get token from BotFather on Telegram
TOKEN="123456789:ABCDEFGHIjklmnopqrstuvwxyz_EXAMPLE"
ADMIN_ID="123456789"
API_KEY="sk-or-v1-abcdef"
URL="https://hermes-telegram-production.up.railway.app"

# 2. Deploy to Railway
cd ~/projects/hermes-agent
railway init
railway variables set TELEGRAM_BOT_TOKEN=$TOKEN
railway variables set TELEGRAM_ADMIN_USER_ID=$ADMIN_ID
railway variables set OPENROUTER_API_KEY=$API_KEY
git push origin main

# 3. Wait 2-3 minutes for deployment

# 4. Set webhook
curl -X POST "https://api.telegram.org/bot${TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"${URL}/telegram/webhook\"}"

# 5. Test on Telegram
# Open Telegram → Search for your bot → Send /help
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `src/gateway/telegram_enhanced.py` | Main bot logic |
| `src/gateway/telegram_setup.py` | Setup wizard |
| `docs/TELEGRAM_QUICK_START.md` | Full guide |
| `.env.telegram` | Your config (don't commit!) |
| `railway.toml` | Railway deployment config |

---

## Check Status

```bash
# Is Railway running?
railway logs | head -20

# Is webhook connected?
TOKEN="your_token"
curl "https://api.telegram.org/bot${TOKEN}/getWebhookInfo"

# Is bot responding?
# Just send it a message on Telegram
```

---

**Next: Open Telegram and start using your bot!** 🎉
