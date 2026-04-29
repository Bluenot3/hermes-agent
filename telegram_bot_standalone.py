#!/usr/bin/env python3
"""
Standalone Telegram bot for Hermes Agent (LOCAL - NO API KEYS NEEDED).
Uses the local Hermes agent directly, no OpenRouter or paid APIs.

Run with:
    python telegram_bot_standalone.py
"""

import logging
import asyncio
import sys
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = "8783305782:AAExwIlaw9o3hkPTUIrlpMfMJcn2J3DjPxA"
TELEGRAM_ADMIN_USER_ID = 1549382618

# ──────────────────────────────────────────────────────────────
# IMPORTS
# ──────────────────────────────────────────────────────────────

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
    from telegram.constants import ParseMode
except ImportError:
    print("❌ python-telegram-bot not installed")
    print("   Run: pip install 'python-telegram-bot[webhooks]' httpx")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("❌ httpx not installed")
    print("   Run: pip install httpx")
    sys.exit(1)

# Import the local Hermes agent
try:
    from run_agent import AIAgent
    HERMES_AVAILABLE = True
except ImportError:
    print("❌ Could not import Hermes agent")
    print("   Make sure you're in the hermes-agent directory")
    HERMES_AVAILABLE = False

# ──────────────────────────────────────────────────────────────
# HELP & STATUS MESSAGES
# ──────────────────────────────────────────────────────────────

HELP_TEXT = """
<b>🤖 Hermes Agent — Command Reference</b>

<b>General Commands</b>
/help — Show this help message
/status — Check bot and agent status
/ping — Test if bot is alive

<b>Chat with Agent</b>
Just send any message and Hermes will respond.
(Uses your local Hermes installation — completely free, no API keys needed)

<b>Admin Commands</b>
/admin_panel — Show admin dashboard (admin only)
/reset — Clear session memory
"""

# ──────────────────────────────────────────────────────────────
# BOT LOGIC
# ──────────────────────────────────────────────────────────────

class HermesBot:
    def __init__(self, token: str, admin_id: int):
        self.token = token
        self.admin_id = admin_id
        self.app: Optional[Application] = None
        self.agent: Optional[AIAgent] = None
        self.conversation_history = {}  # Per-user message history

    async def verify_bot_identity(self) -> None:
        """Check that the bot token is valid."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.telegram.org/bot{self.token}/getMe")
            resp.raise_for_status()
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API error: {data}")
            bot_info = data["result"]
            logger.info(f"✅ Connected as @{bot_info.get('username', '?')} (ID: {bot_info.get('id')})")

    def _init_hermes_agent(self) -> None:
        """Initialize the local Hermes agent."""
        if not HERMES_AVAILABLE:
            logger.warning("⚠️  Hermes agent not available")
            return
        
        try:
            # Create agent instance (uses local config from ~/.hermes)
            self.agent = AIAgent(
                quiet_mode=True,  # Don't spam CLI output
            )
            logger.info("✅ Hermes agent initialized (LOCAL)")
        except Exception as exc:
            logger.warning(f"⚠️  Could not initialize Hermes: {exc}")

    def is_allowed(self, user_id: int) -> bool:
        return user_id == self.admin_id

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        hermes_status = "✅ Hermes available (LOCAL)" if self.agent else "⚠️  Hermes not available"
        text = (
            f"<b>🤖 Hermes Agent Status</b>\n\n"
            f"{hermes_status}\n"
            f"💻 Mode: Local (no API fees)\n"
            f"👤 User ID: {update.effective_user.id}\n"
            f"🔒 Auth: {'✅ Authorized' if self.is_allowed(update.effective_user.id) else '❌ Not authorized'}"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_ping(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🏓 Pong! Bot is alive and responding.")

    async def cmd_admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user.id != self.admin_id:
            await update.message.reply_text("⛔ Admin access required.")
            return
        text = (
            "<b>🛡️ Admin Panel</b>\n\n"
            f"• Admin User ID: {self.admin_id}\n"
            f"• Hermes: {'✅ Ready' if self.agent else '❌ Not loaded'}\n"
            f"• Mode: 🆓 Free (local only)\n"
            f"• Polling Mode: ✅ Active"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_id = update.effective_user.id
        if user_id in self.conversation_history:
            del self.conversation_history[user_id]
        await update.message.reply_text("🔄 Session reset.")

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle free-form text messages."""
        user_msg = update.message.text or ""
        user_id = update.effective_user.id
        
        # Check authorization
        if not self.is_allowed(user_id):
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return

        # Show thinking
        thinking = await update.message.reply_text("⏳ Thinking…")

        try:
            # Call Hermes Agent
            response = await self.call_agent(user_id, user_msg)
            await thinking.delete()
            
            # Send response in chunks (Telegram 4096 char limit)
            for chunk in self.chunk_message(response, 4096):
                await update.message.reply_text(chunk)
        except Exception as exc:
            logger.exception("Agent error")
            await thinking.edit_text(f"❌ Error: {str(exc)[:200]}")

    async def call_agent(self, user_id: int, user_message: str) -> str:
        """Call the local Hermes Agent and return its response."""
        if not self.agent:
            return "⚠️  Hermes agent is not available. Make sure you're in the hermes-agent directory."

        try:
            # Initialize conversation history for this user if needed
            if user_id not in self.conversation_history:
                self.conversation_history[user_id] = []

            # Run the agent with the user's message
            result = self.agent.run_conversation(
                user_message=user_message,
                conversation_history=self.conversation_history[user_id],
            )

            # Update conversation history for next turn
            if "messages" in result:
                self.conversation_history[user_id] = result["messages"]

            # Return the final response
            return result.get("final_response", "I didn't get a response from the agent.")

        except Exception as exc:
            logger.exception("Agent call failed")
            return f"❌ Error: {str(exc)}"

    @staticmethod
    def chunk_message(text: str, max_len: int = 4096) -> list:
        """Split message into chunks to respect Telegram's size limit."""
        if len(text) <= max_len:
            return [text]
        
        chunks = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > max_len:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += ("\n" + line if current else line)
        if current:
            chunks.append(current)
        return chunks

    async def setup(self) -> None:
        """Initialize the bot application."""
        self.app = Application.builder().token(self.token).build()
        
        # Add handlers
        self.app.add_handler(CommandHandler("start", self.cmd_help))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("ping", self.cmd_ping))
        self.app.add_handler(CommandHandler("admin_panel", self.cmd_admin_panel))
        self.app.add_handler(CommandHandler("reset", self.cmd_reset))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))

    async def run(self) -> None:
        """Start the bot (polling mode)."""
        await self.verify_bot_identity()
        self._init_hermes_agent()
        await self.setup()
        
        logger.info("🚀 Starting bot in long-polling mode...")
        logger.info(f"📱 Send messages to @zenxhermesbot")
        logger.info(f"👤 Authorized user: {self.admin_id}")
        logger.info(f"💻 Using LOCAL Hermes (no API fees)")
        
        if self.app:
            await self.app.initialize()
            await self.app.start()
            await self.app.run_polling(drop_pending_updates=True)


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

async def main():
    bot = HermesBot(
        token=TELEGRAM_BOT_TOKEN,
        admin_id=TELEGRAM_ADMIN_USER_ID,
    )
    await bot.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as exc:
        logger.exception(f"Fatal error: {exc}")
        sys.exit(1)
