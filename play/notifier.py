"""Telegram notification sender for complaint escalation alerts.

Sends escalation alerts to the USER (never to the landlord directly).
Each alert includes the full drafted message in a monospace block so the
user can copy-paste it directly from Telegram.

Handles API failures gracefully — never crashes the run.

Ported from document-expiry-watchdog notifier with adapted message format.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Telegram Bot API endpoint
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _load_env_file() -> None:
    """Load key-value pairs from .env file into os.environ if present."""
    env_path = Path(".env")
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception as e:
            logger.warning("Could not read .env file: %s", e)


def _get_telegram_config() -> tuple[str, str]:
    """Read Telegram credentials from environment or .env file.

    Returns:
        (bot_token, chat_id) tuple

    Raises:
        ValueError: If either env var is missing or empty
    """
    _load_env_file()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN not set. "
            "Create a bot via @BotFather on Telegram and set the token in .env."
        )
    if not chat_id:
        raise ValueError(
            "TELEGRAM_CHAT_ID not set. "
            "Message @userinfobot on Telegram to get your chat ID and set it in .env."
        )

    return token, chat_id


def format_escalation_alert(
    complaint_id: str,
    description: str,
    category: str,
    escalation_level: int,
    days_overdue: int,
    days_since_reported: int,
    contact: str,
    drafted_message: str,
) -> str:
    """Format an escalation alert message for Telegram.

    Includes the full drafted message in a monospace block so the user
    can copy-paste it directly.
    """
    level_labels = {
        1: "Polite Reminder",
        2: "Firm Follow-up",
        3: "Formal Notice",
    }
    level_label = level_labels.get(
        escalation_level,
        f"Formal Notice (Level {escalation_level})",
    )

    level_emojis = {1: "📋", 2: "⚠️", 3: "🚨"}
    emoji = level_emojis.get(escalation_level, "🚨")

    category_display = category.replace("_", " ").title() if category else "General"

    message = (
        f"{emoji} *ESCALATION ALERT — Level {escalation_level}*\n"
        f"_{level_label}_\n"
        f"\n"
        f"*Complaint:* #{complaint_id} — {description}\n"
        f"*Category:* {category_display}\n"
        f"*Days since report:* {days_since_reported}\n"
        f"*Days overdue:* {days_overdue}\n"
        f"*Contact:* {contact}\n"
        f"\n"
        f"— — — — — — — — — —\n"
        f"*Ready-to-send message (copy and paste):*\n"
        f"— — — — — — — — — —\n"
        f"\n"
        f"```\n"
        f"{drafted_message}\n"
        f"```\n"
        f"\n"
        f"_Review the message above, personalize if needed, then send it "
        f"to your landlord/building management._"
    )

    return message


def send_escalation_alert(
    complaint_id: str,
    description: str,
    category: str,
    escalation_level: int,
    days_overdue: int,
    days_since_reported: int,
    contact: str,
    drafted_message: str,
) -> bool:
    """Send an escalation alert via Telegram to the USER.

    Returns:
        True if notification was sent successfully, False otherwise.
        Never raises — all errors are logged and swallowed.
    """
    try:
        token, chat_id = _get_telegram_config()
    except ValueError as e:
        logger.error("Telegram config error: %s", e)
        return False

    message = format_escalation_alert(
        complaint_id=complaint_id,
        description=description,
        category=category,
        escalation_level=escalation_level,
        days_overdue=days_overdue,
        days_since_reported=days_since_reported,
        contact=contact,
        drafted_message=drafted_message,
    )

    return _send_telegram_message(token, chat_id, message)


def _send_telegram_message(token: str, chat_id: str, message: str) -> bool:
    """Send a message via Telegram Bot API.

    Uses urllib (no requests dependency needed) to minimize external deps.

    Returns:
        True if sent successfully, False on any failure.
    """
    url = TELEGRAM_API_URL.format(token=token)

    payload = json.dumps({
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=10) as response:
            response_data = json.loads(response.read().decode("utf-8"))
            if response_data.get("ok"):
                logger.info("Telegram notification sent successfully.")
                return True
            else:
                logger.error(
                    "Telegram API returned ok=false: %s",
                    response_data.get("description", "unknown error"),
                )
                return False

    except HTTPError as e:
        status_code = e.code
        try:
            error_body = json.loads(e.read().decode("utf-8"))
            description = error_body.get("description", str(e))
        except Exception:
            description = str(e)

        if status_code == 401:
            logger.error("Telegram auth failed (bad token): %s", description)
        elif status_code == 429:
            logger.error("Telegram rate limit exceeded: %s", description)
        elif status_code == 400:
            logger.error(
                "Telegram bad request (check chat_id): %s", description,
            )
        else:
            logger.error(
                "Telegram API error (HTTP %d): %s", status_code, description,
            )
        return False

    except URLError as e:
        logger.error("Telegram network error: %s", e.reason)
        return False

    except Exception as e:
        logger.error(
            "Unexpected error sending Telegram notification: %s", e,
        )
        return False
