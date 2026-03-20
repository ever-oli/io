"""Simple context compression hooks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ContextCompressor:
    enabled: bool = True
    threshold_messages: int = 20
    keep_last: int = 8

    def should_compress(self, messages: list[dict[str, Any]]) -> bool:
        return self.enabled and len(messages) > self.threshold_messages

    def compress(self, messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str] | None:
        if not self.should_compress(messages):
            return None
        to_summarize = messages[:-self.keep_last]
        summary_lines = []
        for message in to_summarize:
            role = message.get("role", "message")
            text = str(message.get("content", "")).strip().replace("\n", " ")
            if text:
                summary_lines.append(f"{role}: {text[:120]}")
        summary = "Conversation summary:\n" + "\n".join(summary_lines[-10:])
        compressed = [{"role": "system", "content": summary}, *messages[-self.keep_last :]]
        return compressed, summary

