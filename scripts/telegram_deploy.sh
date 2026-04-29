#!/usr/bin/env bash
# scripts/telegram_deploy.sh
#
# One-click deploy script for the Hermes Agent Telegram bot.
#
# Usage:
#   bash scripts/telegram_deploy.sh
#
# Prerequisites:
#   - Railway CLI: npm install -g @railway/cli
#   - Logged in: railway login
#   - .env.telegram file with your credentials (see .env.telegram.example)
#
# The script will:
#   1. Read credentials from .env.telegram (if present) or interactive prompts
#   2. Push environment variables to Railway
#   3. Deploy the application
#   4. Register the Telegram webhook
#   5. Verify the setup

set -euo pipefail

# ── helpers ────────────────────────────────────────────────────────────────────

info()    { echo "ℹ  $*"; }
success() { echo "✅ $*"; }
error()   { echo "❌ $*" >&2; }
ask()     { read -rp "  $1: " "$2"; }

# ── load .env.telegram if present ─────────────────────────────────────────────

if [[ -f ".env.telegram" ]]; then
    info "Loading credentials from .env.telegram"
    # shellcheck disable=SC1091
    set -o allexport
    source .env.telegram
    set +o allexport
fi

# ── collect required variables ────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_ADMIN_USER_ID="${TELEGRAM_ADMIN_USER_ID:-}"
OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}"

if [[ -z "$TELEGRAM_BOT_TOKEN" ]]; then
    ask "Telegram Bot Token (from @BotFather)" TELEGRAM_BOT_TOKEN
fi
if [[ -z "$TELEGRAM_ADMIN_USER_ID" ]]; then
    ask "Your Telegram User ID (from @userinfobot)" TELEGRAM_ADMIN_USER_ID
fi
if [[ -z "$OPENROUTER_API_KEY" ]]; then
    ask "OpenRouter API Key (from openrouter.ai/keys)" OPENROUTER_API_KEY
fi

# ── validate railway CLI ───────────────────────────────────────────────────────

if ! command -v railway &>/dev/null; then
    error "Railway CLI not found. Install it with: npm install -g @railway/cli"
    exit 1
fi

# ── deploy to Railway ─────────────────────────────────────────────────────────

info "Setting Railway environment variables…"
railway variables set \
    TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
    TELEGRAM_ADMIN_USER_ID="$TELEGRAM_ADMIN_USER_ID" \
    OPENROUTER_API_KEY="$OPENROUTER_API_KEY"

info "Deploying to Railway…"
railway up --detach

# Retrieve deployment URL
RAILWAY_URL="$(railway status --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url',''))" 2>/dev/null || true)"

if [[ -n "$RAILWAY_URL" ]]; then
    WEBHOOK_URL="https://$RAILWAY_URL"
    info "Registering webhook: $WEBHOOK_URL/telegram/webhook"
    railway variables set TELEGRAM_WEBHOOK_URL="$WEBHOOK_URL"

    sleep 5  # Allow the service to start

    RESPONSE="$(curl -sf -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
        -H "Content-Type: application/json" \
        -d "{\"url\": \"${WEBHOOK_URL}/telegram/webhook\"}" || true)"

    if echo "$RESPONSE" | grep -q '"ok":true'; then
        success "Webhook registered successfully"
    else
        error "Webhook registration may have failed — check manually:"
        echo "  curl https://api.telegram.org/bot\$TOKEN/getWebhookInfo"
    fi
else
    info "Could not determine Railway URL automatically."
    info "After deployment completes, set the webhook manually:"
    echo "  TOKEN=\$TELEGRAM_BOT_TOKEN"
    echo "  URL=https://your-app.up.railway.app"
    echo "  curl -X POST \"https://api.telegram.org/bot\${TOKEN}/setWebhook\" \\"
    echo "       -d \"{\\\"url\\\": \\\"\${URL}/telegram/webhook\\\"}\""
fi

success "Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. Open Telegram and search for your bot"
echo "  2. Send /start or /help"
echo "  3. Monitor logs with: railway logs --follow"
