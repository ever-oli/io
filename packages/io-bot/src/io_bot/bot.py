"""Telegram Bot integration for IO."""

import os
import requests
from pathlib import Path
from typing import Optional


def load_env(env_file: Optional[Path] = None) -> None:
    """Load environment variables from .env file."""
    if env_file is None:
        env_file = Path.home() / ".config/io-bot/.env"

    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key, value)


class TelegramBot:
    """Telegram Bot for sending messages and notifications."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize Telegram Bot.

        Args:
            token: Bot token (or from TELEGRAM_BOT_TOKEN env var)
            chat_id: Default chat ID (or from TELEGRAM_CHAT_ID env var)
        """
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.default_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")

        if not self.token:
            raise ValueError("Telegram bot token required. Set TELEGRAM_BOT_TOKEN env var.")

    def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
    ) -> bool:
        """
        Send message to Telegram.

        Args:
            text: Message text (HTML formatted)
            chat_id: Chat ID to send to (uses default if not specified)
            parse_mode: Message parse mode (HTML, Markdown, etc.)
            disable_web_page_preview: Whether to disable link previews

        Returns:
            True if sent successfully, False otherwise
        """
        target_chat = chat_id or self.default_chat_id

        if not target_chat:
            raise ValueError("Chat ID required. Set TELEGRAM_CHAT_ID or pass chat_id.")

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        # Telegram has a 4096 character limit for messages
        MAX_LENGTH = 4000

        if len(text) > MAX_LENGTH:
            # Find a good breaking point
            break_point = text.rfind("\n\n", 0, MAX_LENGTH)
            if break_point == -1:
                break_point = text.rfind(". ", 0, MAX_LENGTH)
            if break_point == -1:
                break_point = MAX_LENGTH
            text = text[:break_point] + "\n\n<i>📄 Message truncated</i>"

        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }

        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Telegram error: {e}")
            return False

    def send_notification(self, title: str, message: str) -> bool:
        """Send a simple notification."""
        text = f"<b>{title}</b>\n\n{message}"
        return self.send_message(text)


def send_telegram_message(
    text: str, token: Optional[str] = None, chat_id: Optional[str] = None
) -> bool:
    """
    Convenience function to send a Telegram message.

    Args:
        text: Message text
        token: Bot token (or from TELEGRAM_BOT_TOKEN env var)
        chat_id: Chat ID (or from TELEGRAM_CHAT_ID env var)

    Returns:
        True if sent successfully
    """
    load_env()

    token = token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not token:
        print("TELEGRAM_BOT_TOKEN not set")
        return False

    if not chat_id:
        print("TELEGRAM_CHAT_ID not set")
        return False

    bot = TelegramBot(token=token, chat_id=chat_id)
    return bot.send_message(text)
