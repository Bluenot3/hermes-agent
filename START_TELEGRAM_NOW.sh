#!/bin/bash
set -e

echo "🚀 Starting Hermes Telegram Bot..."
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Install Python 3.10+ first."
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip install -q python-telegram-bot fastapi uvicorn aiohttp

# Start the bot
echo "✅ Bot starting on localhost:8443"
echo ""
echo "📱 Open Telegram and find your bot by its username (from @BotFather)"
echo "💬 Type /help to see all commands"
echo ""

python -m src.api.telegram_gateway
