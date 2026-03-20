"""Gateway platform adapter interfaces for IO."""

from .api_server import APIServerAdapter
from .base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
from .dingtalk import DingTalkAdapter
from .discord import DiscordAdapter
from .email import EmailAdapter
from .homeassistant import HomeAssistantAdapter
from .matrix import MatrixAdapter
from .mattermost import MattermostAdapter
from .signal import SignalAdapter
from .slack import SlackAdapter
from .sms import SmsAdapter
from .telegram import TelegramAdapter
from .webhook import WebhookAdapter
from .whatsapp import WhatsAppAdapter

__all__ = [
    "APIServerAdapter",
    "BasePlatformAdapter",
    "DingTalkAdapter",
    "DiscordAdapter",
    "EmailAdapter",
    "HomeAssistantAdapter",
    "MatrixAdapter",
    "MattermostAdapter",
    "MessageEvent",
    "MessageType",
    "SendResult",
    "SignalAdapter",
    "SlackAdapter",
    "SmsAdapter",
    "TelegramAdapter",
    "WebhookAdapter",
    "WhatsAppAdapter",
]
