"""
FastAPI Telegram Gateway.

Exposes:
  POST /telegram/webhook  — Telegram webhook endpoint
  GET  /health            — Health-check (Railway, k8s probes)
  GET  /status            — Detailed status JSON

Run locally:
    uvicorn src.api.telegram_gateway:app --host 0.0.0.0 --port 8443 --reload

Or via the convenience CLI entry-point:
    python -m src.api.telegram_gateway
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict

logger = logging.getLogger(__name__)

# ── optional FastAPI ──────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException, Request, Response
    from fastapi.responses import JSONResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning(
        "FastAPI not installed. Install with: pip install fastapi uvicorn"
    )

# ── optional telegram ─────────────────────────────────────────────────────────

try:
    from telegram import Update

    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None  # type: ignore

from src.config.telegram_config import TelegramConfig, load_config
from src.gateway.telegram_bot import TelegramBot
from src.gateway.telegram_startup import TelegramStartup

# ── module-level singletons (created during lifespan) ────────────────────────

_config: TelegramConfig | None = None
_bot: TelegramBot | None = None
_ptb_app: Any | None = None  # python-telegram-bot Application
_polling_task: asyncio.Task | None = None


# ── lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def _lifespan(app: "FastAPI") -> AsyncGenerator[None, None]:
    """Initialize the bot on startup and clean up on shutdown."""
    global _config, _bot, _ptb_app

    _config = load_config()
    _bot = TelegramBot(_config)

    # Run startup checks (webhook registration, DB init, identity verify)
    startup = TelegramStartup(_config)
    await startup.run()

    if TELEGRAM_AVAILABLE:
        _ptb_app = _bot._build_application()
        await _ptb_app.initialize()
        if _config.use_webhook:
            await _ptb_app.start()
        else:
            # Polling runs in a background task; keep a reference so it isn't GC'd.
            _polling_task = asyncio.create_task(_ptb_app.run_polling(drop_pending_updates=True))
            _polling_task.add_done_callback(
                lambda t: logger.exception("Polling task ended unexpectedly: %s", t.exception())
                if not t.cancelled() and t.exception() is not None
                else None
            )

    logger.info("Telegram gateway is ready")

    yield  # ── server is running ─────────────────────────────────────────────

    logger.info("Shutting down Telegram gateway")
    if _polling_task is not None and not _polling_task.done():
        _polling_task.cancel()
        try:
            await _polling_task
        except (asyncio.CancelledError, Exception):
            pass
    if _ptb_app is not None:
        try:
            await _ptb_app.stop()
            await _ptb_app.shutdown()
        except Exception as exc:
            logger.warning("Error during bot shutdown: %s", exc)


# ── FastAPI app ───────────────────────────────────────────────────────────────

if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="Hermes Agent — Telegram Gateway",
        description="Webhook and polling gateway that connects Telegram to the Hermes AI Agent.",
        version="1.0.0",
        lifespan=_lifespan,
    )

    # ── routes ────────────────────────────────────────────────────────────────

    @app.get("/health")
    async def health() -> Dict[str, str]:
        """Health-check endpoint for Railway / k8s probes."""
        return {"status": "ok"}

    @app.get("/status")
    async def status() -> Dict[str, Any]:
        """Return bot status information."""
        if _config is None:
            return {"ready": False, "reason": "not initialized"}

        return {
            "ready": True,
            "webhook_mode": _config.use_webhook,
            "model": _config.default_model,
            "rate_limit_per_minute": _config.rate_limit_messages_per_minute,
        }

    @app.post("/telegram/webhook")
    async def telegram_webhook(request: Request) -> Response:
        """Receive an update from Telegram and dispatch it to python-telegram-bot."""
        if _ptb_app is None or not TELEGRAM_AVAILABLE:
            raise HTTPException(status_code=503, detail="Bot not initialised")

        # Optionally verify the webhook secret header
        if _config and _config.webhook_secret:
            secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if secret != _config.webhook_secret:
                raise HTTPException(status_code=403, detail="Invalid secret")

        body = await request.json()
        update = Update.de_json(body, _ptb_app.bot)
        await _ptb_app.process_update(update)
        return Response(status_code=200)

else:
    # Stub so that imports don't crash when FastAPI is absent.
    app = None  # type: ignore


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    """Start the gateway server (convenience wrapper)."""
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn", file=sys.stderr)
        sys.exit(1)

    port = int(os.environ.get("PORT", "8443"))
    uvicorn.run(
        "src.api.telegram_gateway:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=os.environ.get("DEBUG", "").lower() in ("1", "true"),
    )


if __name__ == "__main__":
    main()
