"""IO-style base platform adapter interface for IO."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable

from ..gateway_models import Platform, PlatformConfig
from ..gateway_session import SessionSource


class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    COMMAND = "command"


@dataclass(slots=True)
class MessageEvent:
    source: SessionSource
    text: str = ""
    message_type: MessageType = MessageType.TEXT
    message_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    attachments: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class BasePlatformAdapter(ABC):
    """Common interface for live messaging platform adapters."""

    def __init__(self, *, platform: Platform, config: PlatformConfig) -> None:
        self.platform = platform
        self.config = config
        self._message_handler: Callable[[MessageEvent], Awaitable[None]] | None = None
        self._running = False

    def set_message_handler(
        self,
        handler: Callable[[MessageEvent], Awaitable[None]],
    ) -> None:
        self._message_handler = handler

    async def emit(self, event: MessageEvent) -> None:
        if self._message_handler is None:
            return
        await self._message_handler(event)

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        self._running = True
        await self._start()

    async def stop(self) -> None:
        try:
            await self._stop()
        finally:
            self._running = False

    async def healthcheck(self) -> dict[str, Any]:
        return {
            "platform": self.platform.value,
            "state": "running" if self._running else "stopped",
        }

    async def poll_once(self, *, timeout: float = 0.0) -> list[MessageEvent]:
        del timeout
        return []

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    @abstractmethod
    async def _start(self) -> None:
        """Initialize adapter resources."""

    @abstractmethod
    async def _stop(self) -> None:
        """Release adapter resources."""

    @abstractmethod
    async def send_message(
        self,
        chat_id: str,
        content: str,
        *,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deliver a message to the underlying platform."""
