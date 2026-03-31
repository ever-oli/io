"""IO Bot - Telegram bot for morning briefings and notifications."""

__version__ = "0.1.0"
__release_date__ = "2026-03-31"

from .bot import TelegramBot, send_telegram_message
from .briefing import MorningBriefing

__all__ = ["TelegramBot", "send_telegram_message", "MorningBriefing"]
