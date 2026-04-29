"""
Telegram bot configuration.

All credentials are read exclusively from environment variables — never
hardcoded.  Set them in your `.env` file (see `.env.telegram.example`) or
via your deployment platform (Railway, Docker, etc.).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TelegramConfig:
    """Runtime configuration for the Telegram bot integration."""

    # ── credentials ────────────────────────────────────────────────────────
    bot_token: str = field(
        default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", "")
    )

    # ── access control ──────────────────────────────────────────────────────
    admin_user_id: Optional[int] = field(
        default_factory=lambda: _parse_int_env("TELEGRAM_ADMIN_USER_ID")
    )
    allowed_users: List[int] = field(
        default_factory=lambda: _parse_int_list_env("TELEGRAM_ALLOWED_USERS")
    )

    # ── webhook ──────────────────────────────────────────────────────────────
    webhook_url: Optional[str] = field(
        default_factory=lambda: os.environ.get("TELEGRAM_WEBHOOK_URL")
    )
    webhook_port: int = field(
        default_factory=lambda: int(os.environ.get("TELEGRAM_WEBHOOK_PORT", "8443"))
    )
    webhook_secret: Optional[str] = field(
        default_factory=lambda: os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    )

    # ── model provider ──────────────────────────────────────────────────────
    openrouter_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", "")
    )
    default_model: str = field(
        default_factory=lambda: os.environ.get(
            "HERMES_DEFAULT_MODEL", "anthropic/claude-3.5-sonnet"
        )
    )

    # ── rate limiting ────────────────────────────────────────────────────────
    rate_limit_messages_per_minute: int = field(
        default_factory=lambda: int(
            os.environ.get("TELEGRAM_RATE_LIMIT_PER_MINUTE", "30")
        )
    )

    # ── timeouts ─────────────────────────────────────────────────────────────
    request_timeout: int = field(
        default_factory=lambda: int(os.environ.get("TELEGRAM_REQUEST_TIMEOUT", "30"))
    )
    agent_timeout: int = field(
        default_factory=lambda: int(os.environ.get("TELEGRAM_AGENT_TIMEOUT", "300"))
    )

    # ── session storage ───────────────────────────────────────────────────────
    session_db_path: str = field(
        default_factory=lambda: os.environ.get(
            "TELEGRAM_SESSION_DB", "telegram_sessions.db"
        )
    )

    def validate(self) -> None:
        """Raise ValueError if required fields are missing or invalid."""
        if not self.bot_token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN environment variable is required. "
                "Get a token from @BotFather on Telegram."
            )
        if not self.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable is required. "
                "Get a key at https://openrouter.ai/keys"
            )

    @property
    def use_webhook(self) -> bool:
        """Return True when webhook mode is configured."""
        return bool(self.webhook_url)

    def is_allowed_user(self, user_id: int) -> bool:
        """Return True if *user_id* is permitted to use the bot."""
        if self.admin_user_id and user_id == self.admin_user_id:
            return True
        if self.allowed_users:
            return user_id in self.allowed_users
        # When no allowlist is configured and GATEWAY_ALLOW_ALL_USERS is set,
        # fall back to the gateway-wide open-access flag.
        return os.environ.get("GATEWAY_ALLOW_ALL_USERS", "false").lower() == "true"

    def is_admin(self, user_id: int) -> bool:
        """Return True when *user_id* is the configured admin."""
        return bool(self.admin_user_id and user_id == self.admin_user_id)


# ── helpers ──────────────────────────────────────────────────────────────────


def _parse_int_env(name: str) -> Optional[int]:
    """Return the integer value of env var *name*, or None if unset/invalid."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_int_list_env(name: str) -> List[int]:
    """Return a list of ints from a comma-separated env var."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    result: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        try:
            result.append(int(part))
        except ValueError:
            pass
    return result


def load_config() -> TelegramConfig:
    """Load and return the validated Telegram configuration."""
    cfg = TelegramConfig()
    cfg.validate()
    return cfg
