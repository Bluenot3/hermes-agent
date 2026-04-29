"""
Hermes Agent — Telegram bot.

Provides a full-featured bot that wraps the Hermes Agent conversation
engine and exposes it over Telegram.

Features
--------
- /help, /status, /load, /code, /test, /exec, /deploy, /admin_panel commands
- File upload support (forwards to agent for analysis)
- Inline approval buttons for dangerous commands
- Per-user session memory
- Rate limiting
- Streaming tool output via message edits

Usage
-----
    from src.gateway.telegram_bot import TelegramBot
    from src.config.telegram_config import load_config

    cfg = load_config()
    bot = TelegramBot(cfg)
    bot.run()           # starts polling or webhook depending on cfg.use_webhook
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── optional telegram library ─────────────────────────────────────────────────

try:
    from telegram import (
        Bot,
        InlineKeyboardButton,
        InlineKeyboardMarkup,
        Message,
        Update,
    )
    from telegram.constants import ParseMode
    from telegram.ext import (
        Application,
        CallbackQueryHandler,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning(
        "python-telegram-bot not installed. "
        "Install with: pip install 'python-telegram-bot[webhooks]'"
    )

from src.config.telegram_config import TelegramConfig
from src.utils.telegram_utils import (
    RateLimiter,
    SessionManager,
    chunk_message,
    format_html,
    truncate,
)

# ── agent import (graceful fallback for unit tests) ───────────────────────────

try:
    from run_agent import AIAgent  # type: ignore

    AGENT_AVAILABLE = True
except Exception:  # pragma: no cover
    AGENT_AVAILABLE = False
    AIAgent = None  # type: ignore


# ── Help text ─────────────────────────────────────────────────────────────────

_HELP_TEXT = """
<b>🤖 Hermes Agent — Command Reference</b>

<b>General</b>
/help           — Show this help message
/status         — Check bot and agent status
/cancel         — Cancel the current task

<b>Project</b>
/load &lt;project&gt; — Load a project context
/code &lt;path&gt;    — Review a code file or directory
/test           — Run the project test suite

<b>Execution</b> <i>(requires approval)</i>
/exec &lt;cmd&gt;     — Execute a shell command
/deploy &lt;env&gt;   — Deploy to staging or production

<b>Admin</b>
/admin_panel    — Show admin dashboard
/logs [N]       — Show last N log lines (default 20)
/stats          — Show usage statistics

<b>Free-form chat</b>
Just send any message and the agent will respond.
You can also send files for code review.
""".strip()


# ── Bot ───────────────────────────────────────────────────────────────────────


class TelegramBot:
    """High-level Telegram bot backed by the Hermes AI Agent."""

    def __init__(self, config: TelegramConfig) -> None:
        self.config = config
        self._sessions = SessionManager(config.session_db_path)
        self._rate_limiter = RateLimiter(config.rate_limit_messages_per_minute)
        # pending approval actions: action_id → (chat_id, message_id, command)
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the bot (blocking).  Uses webhook or polling per config."""
        if not TELEGRAM_AVAILABLE:
            raise RuntimeError(
                "python-telegram-bot is not installed. "
                "Run: pip install 'python-telegram-bot[webhooks]'"
            )

        app = self._build_application()

        if self.config.use_webhook:
            logger.info("Starting in webhook mode: %s", self.config.webhook_url)
            app.run_webhook(
                listen="0.0.0.0",
                port=self.config.webhook_port,
                url_path="/telegram/webhook",
                webhook_url=self.config.webhook_url,
                secret_token=self.config.webhook_secret,
            )
        else:
            logger.info("Starting in long-polling mode")
            app.run_polling(drop_pending_updates=True)

    def _build_application(self) -> "Application":
        app = (
            Application.builder()
            .token(self.config.bot_token)
            .read_timeout(self.config.request_timeout)
            .write_timeout(self.config.request_timeout)
            .build()
        )

        # Register command handlers
        app.add_handler(CommandHandler("start", self._cmd_help))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("status", self._cmd_status))
        app.add_handler(CommandHandler("load", self._cmd_load))
        app.add_handler(CommandHandler("code", self._cmd_code))
        app.add_handler(CommandHandler("test", self._cmd_test))
        app.add_handler(CommandHandler("exec", self._cmd_exec))
        app.add_handler(CommandHandler("deploy", self._cmd_deploy))
        app.add_handler(CommandHandler("admin_panel", self._cmd_admin_panel))
        app.add_handler(CommandHandler("logs", self._cmd_logs))
        app.add_handler(CommandHandler("stats", self._cmd_stats))
        app.add_handler(CommandHandler("cancel", self._cmd_cancel))

        # Inline keyboard callback
        app.add_handler(CallbackQueryHandler(self._on_callback_query))

        # Free-form messages and file uploads
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text)
        )
        app.add_handler(
            MessageHandler(filters.Document.ALL, self._on_document)
        )

        return app

    # ── access guard ──────────────────────────────────────────────────────────

    def _is_allowed(self, user_id: int) -> bool:
        return self.config.is_allowed_user(user_id)

    async def _guard(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> bool:
        """Return False and reply with an error if the user is not allowed."""
        if update.effective_user is None:
            return False
        uid = update.effective_user.id
        if not self._is_allowed(uid):
            await update.message.reply_text(
                "⛔ You are not authorised to use this bot."
            )
            return False
        if not self._rate_limiter.is_allowed(uid):
            wait = self._rate_limiter.seconds_until_reset(uid)
            await update.message.reply_text(
                f"⏳ Rate limit reached. Please wait {wait:.0f}s before sending another message."
            )
            return False
        return True

    # ── command handlers ──────────────────────────────────────────────────────

    async def _cmd_help(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        await update.message.reply_text(_HELP_TEXT, parse_mode=ParseMode.HTML)

    async def _cmd_status(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        session = self._sessions.get_or_create(
            update.effective_user.id, update.effective_chat.id
        )
        project_info = f"📁 Project: <b>{format_html(session.project)}</b>" if session.project else "📁 No project loaded"
        agent_status = "✅ Agent available" if AGENT_AVAILABLE else "⚠️  Agent not available (check config)"
        text = (
            f"<b>🤖 Hermes Agent Status</b>\n\n"
            f"{agent_status}\n"
            f"{project_info}\n"
            f"💬 History: {len(session.history)} turns"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_load(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /load &lt;project-name&gt;", parse_mode=ParseMode.HTML)
            return
        project = " ".join(args)
        session = self._sessions.get_or_create(
            update.effective_user.id, update.effective_chat.id
        )
        session.project = project
        self._sessions.save(session)
        await update.message.reply_text(
            f"✅ Loaded project: <b>{format_html(project)}</b>", parse_mode=ParseMode.HTML
        )

    async def _cmd_code(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /code &lt;path&gt;", parse_mode=ParseMode.HTML)
            return
        path = " ".join(args)
        prompt = f"Please review the code at: {path}"
        await self._run_agent_and_reply(update, prompt)

    async def _cmd_test(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        session = self._sessions.get_or_create(
            update.effective_user.id, update.effective_chat.id
        )
        project_ctx = f" for project '{session.project}'" if session.project else ""
        prompt = f"Run the test suite{project_ctx} and report results."
        await self._run_agent_and_reply(update, prompt)

    async def _cmd_exec(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /exec &lt;command&gt;", parse_mode=ParseMode.HTML)
            return
        command = " ".join(args)
        await self._request_approval(
            update,
            action_type="exec",
            description=f"Execute command:\n<code>{format_html(command)}</code>",
            payload=command,
        )

    async def _cmd_deploy(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        args = context.args
        environment = args[0] if args else "staging"
        await self._request_approval(
            update,
            action_type="deploy",
            description=f"Deploy to <b>{format_html(environment)}</b>?",
            payload=environment,
        )

    async def _cmd_admin_panel(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        if not self.config.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Admin access required.")
            return
        text = (
            "<b>🛡️ Admin Panel</b>\n\n"
            f"• Active sessions: {len(self._sessions._cache)}\n"
            f"• Pending approvals: {len(self._pending_approvals)}\n"
            f"• Rate limit: {self.config.rate_limit_messages_per_minute} msg/min\n"
            f"• Model: {format_html(self.config.default_model)}\n"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def _cmd_logs(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        if not self.config.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Admin access required.")
            return
        n = 20
        if context.args:
            try:
                n = int(context.args[0])
            except ValueError:
                pass
        prompt = f"Show me the last {n} lines of the agent log."
        await self._run_agent_and_reply(update, prompt)

    async def _cmd_stats(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        if not self.config.is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Admin access required.")
            return
        await update.message.reply_text("📊 Stats collection is not yet implemented.")

    async def _cmd_cancel(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        self._sessions.clear(update.effective_user.id)
        await update.message.reply_text("🛑 Session cleared. History and project reset.")

    # ── free-form text ────────────────────────────────────────────────────────

    async def _on_text(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        await self._run_agent_and_reply(update, update.message.text or "")

    # ── file uploads ──────────────────────────────────────────────────────────

    # Allowed MIME type prefixes for uploaded documents.
    _ALLOWED_MIME_PREFIXES = ("text/", "application/json", "application/xml",
                              "application/x-yaml", "application/toml")
    # Maximum file size accepted for text-content reading (2 MB).
    _MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024

    async def _on_document(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        if not await self._guard(update, context):
            return
        doc = update.message.document
        if doc is None:
            return

        # Validate MIME type before downloading.
        mime = (doc.mime_type or "").lower()
        if not any(mime.startswith(p) for p in self._ALLOWED_MIME_PREFIXES):
            await update.message.reply_text(
                "⚠️ Only text-based files (source code, JSON, YAML, etc.) are supported."
            )
            return

        # Validate file size.
        if doc.file_size and doc.file_size > self._MAX_FILE_SIZE_BYTES:
            await update.message.reply_text(
                f"⚠️ File too large ({doc.file_size // 1024} KB). Maximum allowed is 2 MB."
            )
            return

        thinking = await update.message.reply_text("📎 Receiving file…")

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                file = await context.bot.get_file(doc.file_id)
                # Use safe_filename to prevent path traversal.
                from src.utils.telegram_utils import safe_filename
                safe_name = safe_filename(doc.file_name or "upload.bin")
                dest = Path(tmp_dir) / safe_name
                await file.download_to_drive(str(dest))

                # Limit content sent to the agent.
                content = dest.read_text(errors="replace")[:8000]
                caption = update.message.caption or ""
                prompt = (
                    f"The user uploaded a file named '{safe_name}'."
                    + (f" They said: {caption}" if caption else "")
                    + f"\n\nFile content:\n```\n{content}\n```"
                )

            await thinking.delete()
            await self._run_agent_and_reply(update, prompt)
        except Exception as exc:
            logger.exception("Error handling document upload")
            await thinking.edit_text(f"❌ Error processing file: {truncate(str(exc), 200)}")

    # ── approval flow ─────────────────────────────────────────────────────────

    async def _request_approval(
        self,
        update: "Update",
        action_type: str,
        description: str,
        payload: str,
    ) -> None:
        action_id = uuid.uuid4().hex
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Confirm", callback_data=f"approve:{action_id}"),
                    InlineKeyboardButton("❌ Cancel", callback_data=f"deny:{action_id}"),
                ]
            ]
        )
        msg = await update.message.reply_text(
            f"⚠️ {description}\n\nDo you want to proceed?",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        self._pending_approvals[action_id] = {
            "type": action_type,
            "payload": payload,
            "chat_id": msg.chat_id,
            "message_id": msg.message_id,
            "user_id": update.effective_user.id,
        }

    async def _on_callback_query(self, update: "Update", context: "ContextTypes.DEFAULT_TYPE") -> None:
        query = update.callback_query
        await query.answer()

        data = query.data or ""
        if ":" not in data:
            return

        verb, action_id = data.split(":", 1)

        if verb == "status":
            await query.edit_message_text("🔄 Refreshing…")
            await self._cmd_status(update, context)
            return

        pending = self._pending_approvals.pop(action_id, None)
        if pending is None:
            await query.edit_message_text("⚠️ This action has already been handled or expired.")
            return

        if verb == "deny":
            await query.edit_message_text("❌ Action cancelled.")
            return

        # Approved
        await query.edit_message_text("✅ Approved. Running…")
        action_type = pending["type"]
        payload = pending["payload"]

        if action_type == "exec":
            prompt = f"Execute this shell command: {payload}"
        elif action_type == "deploy":
            prompt = f"Deploy the project to {payload}."
        else:
            prompt = payload

        # Re-use update with original chat context for the reply.
        await self._run_agent_and_reply(update, prompt, chat_id=pending["chat_id"])

    # ── agent runner ──────────────────────────────────────────────────────────

    async def _run_agent_and_reply(
        self,
        update: "Update",
        prompt: str,
        chat_id: Optional[int] = None,
    ) -> None:
        """Run the agent and stream chunks back to Telegram."""
        target_chat = chat_id or update.effective_chat.id
        thinking_msg = await update.get_bot().send_message(
            chat_id=target_chat, text="⏳ Thinking…"
        )

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, self._call_agent, update.effective_user.id, target_chat, prompt
            )
        except Exception as exc:
            logger.exception("Agent error")
            await thinking_msg.edit_text(f"❌ Agent error: {truncate(str(exc), 200)}")
            return

        await thinking_msg.delete()

        # Send response in chunks (Telegram 4096-char limit)
        for chunk in chunk_message(response):
            await update.get_bot().send_message(chat_id=target_chat, text=chunk)

    def _call_agent(self, user_id: int, chat_id: int, prompt: str) -> str:
        """Synchronously call the Hermes AIAgent and return its response."""
        if not AGENT_AVAILABLE or AIAgent is None:
            return "⚠️  The Hermes agent is not available. Check that OPENROUTER_API_KEY is set."

        session = self._sessions.get_or_create(user_id, chat_id)

        agent = AIAgent(
            api_key=self.config.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
            model=self.config.default_model,
            platform="telegram",
            quiet_mode=True,
        )

        result = agent.run_conversation(
            user_message=prompt,
            conversation_history=list(session.history),
        )

        # Persist updated history
        session.history = result.get("messages", [])
        self._sessions.save(session)

        return result.get("final_response", "No response.")
