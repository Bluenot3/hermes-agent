"""
Telegram bot startup helper.

Responsibilities:
- Verify bot connectivity (getMe)
- Register the webhook (or delete it for polling mode)
- Initialise the session database
- Log environment summary on startup

Usage (called by telegram_gateway.py at server start):

    from src.gateway.telegram_startup import TelegramStartup
    from src.config.telegram_config import load_config

    cfg = load_config()
    startup = TelegramStartup(cfg)
    await startup.run()
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

from src.config.telegram_config import TelegramConfig
from src.utils.telegram_utils import SessionManager


class TelegramStartup:
    """Performs all pre-flight checks before the bot starts accepting messages."""

    def __init__(self, config: TelegramConfig) -> None:
        self.config = config
        self._api_base = f"https://api.telegram.org/bot{config.bot_token}"

    # ── public entry point ────────────────────────────────────────────────────

    async def run(self) -> None:
        """Run all startup tasks.  Raises on fatal misconfiguration."""
        logger.info("Hermes Telegram Gateway — starting up")

        self._log_env_summary()
        self._init_session_db()
        await self._verify_bot_identity()

        if self.config.use_webhook:
            await self._register_webhook()
        else:
            await self._delete_webhook()

        logger.info("Startup complete — bot is ready")

    # ── sub-tasks ─────────────────────────────────────────────────────────────

    def _log_env_summary(self) -> None:
        logger.info(
            "Configuration: webhook=%s model=%s rate_limit=%d/min",
            "enabled" if self.config.use_webhook else "polling",
            self.config.default_model,
            self.config.rate_limit_messages_per_minute,
        )
        if self.config.admin_user_id:
            logger.info("Admin user ID: %d", self.config.admin_user_id)
        if self.config.allowed_users:
            logger.info("Allowed users: %s", self.config.allowed_users)

    def _init_session_db(self) -> None:
        """Initialise the SQLite session database."""
        logger.info("Initialising session database: %s", self.config.session_db_path)
        SessionManager(self.config.session_db_path)  # creates tables on __init__
        logger.info("Session database ready")

    async def _verify_bot_identity(self) -> None:
        """Call getMe and log the bot's username."""
        if not _HTTPX_AVAILABLE:
            logger.warning(
                "httpx not installed — skipping bot identity check. "
                "Install with: pip install httpx"
            )
            return

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(f"{self._api_base}/getMe")
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise RuntimeError(f"Telegram API error: {data}")
                bot_info = data["result"]
                logger.info(
                    "Connected as @%s (id=%d)",
                    bot_info.get("username", "?"),
                    bot_info.get("id", 0),
                )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to verify bot identity — check TELEGRAM_BOT_TOKEN: {exc}"
            ) from exc

    async def _register_webhook(self) -> None:
        """Register the webhook URL with Telegram."""
        if not _HTTPX_AVAILABLE:
            logger.warning("httpx not installed — skipping webhook registration")
            return

        url = f"{self.config.webhook_url}/telegram/webhook"
        payload: dict = {"url": url}
        if self.config.webhook_secret:
            payload["secret_token"] = self.config.webhook_secret

        logger.info("Registering webhook: %s", url)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self._api_base}/setWebhook", json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    raise RuntimeError(f"setWebhook failed: {data}")
            logger.info("Webhook registered successfully")
        except Exception as exc:
            raise RuntimeError(f"Failed to register webhook: {exc}") from exc

    async def _delete_webhook(self) -> None:
        """Remove any previously registered webhook (switch to polling)."""
        if not _HTTPX_AVAILABLE:
            return

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{self._api_base}/deleteWebhook")
                resp.raise_for_status()
            logger.info("Webhook deleted — using long-polling mode")
        except Exception as exc:
            logger.warning("Could not delete webhook: %s", exc)
