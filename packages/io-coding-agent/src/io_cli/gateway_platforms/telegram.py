"""Telegram platform adapter for IO."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ..commands import telegram_bot_commands
from ..gateway_models import Platform, PlatformConfig
from ..gateway_session import SessionSource
from .base import BasePlatformAdapter, MessageEvent, MessageType


def _env_token() -> str:
    return (
        os.getenv("IO_TELEGRAM_BOT_TOKEN")
        or os.getenv("TELEGRAM_BOT_TOKEN")
        or os.getenv("TELEGRAM_TOKEN")
        or ""
    ).strip()


class TelegramAdapter(BasePlatformAdapter):
    MAX_MESSAGE_LENGTH = 4096

    def __init__(self, config: PlatformConfig) -> None:
        super().__init__(platform=Platform.TELEGRAM, config=config)
        self.token = str(config.token or _env_token()).strip()
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""
        self.offset = int(config.extra.get("offset", 0) or 0)
        self.poll_timeout = float(config.extra.get("poll_timeout", 20.0) or 20.0)

    async def _request_json(
        self,
        method: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("Telegram bot token is not configured.")
        timeout = max(self.poll_timeout + 5.0, 30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{self.base_url}/{method}",
                json=payload or {},
                headers={"User-Agent": "IO-Agent/0.1"},
            )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not data.get("ok"):
            description = ""
            if isinstance(data, dict):
                description = str(data.get("description", "Telegram API request failed."))
            raise RuntimeError(description or "Telegram API request failed.")
        return data

    async def _start(self) -> None:
        await self._request_json("getMe")
        try:
            await self._request_json(
                "setMyCommands",
                payload={
                    "commands": [
                        {"command": name, "description": description[:256]}
                        for name, description in telegram_bot_commands()
                    ]
                },
            )
        except Exception:
            # Command registration is best-effort. The adapter should still run
            # if Telegram rejects the menu update.
            return None

    async def _stop(self) -> None:
        return None

    def _chat_type(self, value: str) -> str:
        if value == "private":
            return "dm"
        if value in {"group", "supergroup"}:
            return "group"
        if value == "channel":
            return "channel"
        return "dm"

    def _file_url(self, file_path: str) -> str:
        normalized = str(file_path or "").lstrip("/")
        return f"https://api.telegram.org/file/bot{self.token}/{normalized}"

    async def _resolve_file_url(self, file_id: str | None) -> str | None:
        file_id = str(file_id or "").strip()
        if not file_id:
            return None
        try:
            data = await self._request_json("getFile", payload={"file_id": file_id})
        except Exception:
            return None
        result = data.get("result")
        if not isinstance(result, dict):
            return None
        file_path = str(result.get("file_path") or "").strip()
        if not file_path:
            return None
        return self._file_url(file_path)

    async def _resolve_attachments(self, message: dict[str, Any]) -> list[str]:
        attachments: list[str] = []

        photo_items = message.get("photo")
        if isinstance(photo_items, list):
            photo = next(
                (
                    item for item in reversed(photo_items)
                    if isinstance(item, dict) and item.get("file_id")
                ),
                None,
            )
            if isinstance(photo, dict):
                url = await self._resolve_file_url(str(photo.get("file_id") or ""))
                label = "photo"
                if url:
                    label = f"{label}: {url}"
                attachments.append(label)

        document = message.get("document")
        if isinstance(document, dict) and document.get("file_id"):
            name = str(document.get("file_name") or "document").strip() or "document"
            url = await self._resolve_file_url(str(document.get("file_id") or ""))
            label = f"document ({name})"
            if url:
                label = f"{label}: {url}"
            attachments.append(label)

        audio = message.get("audio") or message.get("voice")
        if isinstance(audio, dict) and audio.get("file_id"):
            name = str(audio.get("title") or audio.get("file_name") or "audio").strip() or "audio"
            url = await self._resolve_file_url(str(audio.get("file_id") or ""))
            label = f"audio ({name})"
            if url:
                label = f"{label}: {url}"
            attachments.append(label)

        return attachments

    def _parse_message(self, message: dict[str, Any]) -> MessageEvent | None:
        chat = message.get("chat")
        if not isinstance(chat, dict):
            return None
        user = message.get("from")
        if isinstance(user, dict) and user.get("is_bot"):
            return None

        text = str(message.get("text") or message.get("caption") or "").strip()
        message_type = MessageType.TEXT
        if message.get("photo"):
            message_type = MessageType.IMAGE
            if not text:
                text = "[User sent a photo]"
        elif message.get("voice") or message.get("audio"):
            message_type = MessageType.AUDIO
            if not text:
                text = "[User sent audio]"
        elif message.get("document"):
            message_type = MessageType.DOCUMENT
            if not text:
                text = "[User sent a document]"
        if text.startswith("/"):
            message_type = MessageType.COMMAND

        return MessageEvent(
            source=SessionSource(
                platform=Platform.TELEGRAM,
                chat_id=str(chat.get("id", "")),
                chat_name=chat.get("title") or chat.get("username") or chat.get("first_name"),
                chat_type=self._chat_type(str(chat.get("type", "private"))),
                user_id=str(user.get("id")) if isinstance(user, dict) and user.get("id") is not None else None,
                user_name=(
                    user.get("username")
                    or " ".join(
                        part for part in [user.get("first_name"), user.get("last_name")] if part
                    ).strip()
                    or None
                )
                if isinstance(user, dict)
                else None,
                thread_id=(
                    str(message.get("message_thread_id"))
                    if message.get("message_thread_id") is not None
                    else None
                ),
            ),
            text=text,
            message_type=message_type,
            message_id=str(message.get("message_id", "")),
            metadata={"telegram_message": message},
        )

    async def poll_once(self, *, timeout: float = 0.0) -> list[MessageEvent]:
        effective_timeout = max(0, int(timeout if timeout > 0 else self.poll_timeout))
        payload = {
            "offset": self.offset,
            "timeout": effective_timeout,
            "allowed_updates": ["message", "edited_message"],
        }
        data = await self._request_json("getUpdates", payload=payload)
        items = data.get("result", [])
        if not isinstance(items, list):
            return []
        events: list[MessageEvent] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            update_id = item.get("update_id")
            if isinstance(update_id, int):
                self.offset = max(self.offset, update_id + 1)
            message = item.get("message") or item.get("edited_message")
            if not isinstance(message, dict):
                continue
            event = self._parse_message(message)
            if event is not None:
                event.attachments = await self._resolve_attachments(message)
                if event.attachments:
                    event.metadata["attachments"] = list(event.attachments)
                events.append(event)
        self.config.extra["offset"] = self.offset
        return events

    async def send_message(
        self,
        chat_id: str,
        content: str,
        *,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del metadata
        if not chat_id:
            raise RuntimeError("Telegram chat_id is required to send a message.")
        sent_messages: list[dict[str, Any]] = []
        for chunk in self._split_message(content):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if thread_id:
                try:
                    payload["message_thread_id"] = int(thread_id)
                except ValueError:
                    pass
            result = await self._request_json("sendMessage", payload=payload)
            sent_messages.append(result.get("result", {}))
        return {"messages": sent_messages, "count": len(sent_messages)}

    def _split_message(self, content: str) -> list[str]:
        text = str(content or "").strip() or "(no response)"
        if len(text) <= self.MAX_MESSAGE_LENGTH:
            return [text]
        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= self.MAX_MESSAGE_LENGTH:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, self.MAX_MESSAGE_LENGTH)
            if split_at <= 0:
                split_at = self.MAX_MESSAGE_LENGTH
            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()
        return chunks
