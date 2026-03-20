"""Gateway platform adapter interfaces for IO."""

from .base import BasePlatformAdapter, MessageEvent, MessageType
from .telegram import TelegramAdapter

__all__ = [
    "BasePlatformAdapter",
    "MessageEvent",
    "MessageType",
    "TelegramAdapter",
]
