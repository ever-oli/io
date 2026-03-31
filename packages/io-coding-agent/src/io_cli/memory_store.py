"""Cross-session memory system - Claude Code style persistent memory.

Unlike IO's current session-based storage, this provides:
- Persistent memory across sessions
- Memory categories (facts, preferences, project context)
- Automatic memory extraction from conversations
- Memory search and retrieval
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Memory:
    """A single memory entry."""

    id: str
    content: str
    category: str  # "fact", "preference", "project", "task", "error"
    source: str  # Where this memory came from
    created_at: datetime
    access_count: int = 0
    last_accessed: datetime | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Memory:
        return cls(
            id=data["id"],
            content=data["content"],
            category=data["category"],
            source=data["source"],
            created_at=datetime.fromisoformat(data["created_at"]),
            access_count=data.get("access_count", 0),
            last_accessed=datetime.fromisoformat(data["last_accessed"])
            if data.get("last_accessed")
            else None,
            tags=data.get("tags", []),
        )


@dataclass
class MemoryStore:
    """Persistent memory store for IO.

    Stores memories in ~/.io/memory/memories.json
    """

    home: Path

    def __post_init__(self):
        self.memory_dir = self.home / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memories: dict[str, Memory] = {}
        self._load()

    @property
    def _memories_path(self) -> Path:
        return self.memory_dir / "memories.json"

    def _load(self) -> None:
        """Load memories from disk."""
        if self._memories_path.exists():
            try:
                data = json.loads(self._memories_path.read_text())
                for item in data.get("memories", []):
                    try:
                        memory = Memory.from_dict(item)
                        self.memories[memory.id] = memory
                    except (KeyError, ValueError):
                        continue
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        """Save memories to disk."""
        data = {
            "memories": [m.to_dict() for m in self.memories.values()],
            "updated_at": datetime.now().isoformat(),
        }
        self._memories_path.write_text(json.dumps(data, indent=2))

    def add(
        self,
        content: str,
        category: str = "fact",
        source: str = "user",
        tags: list[str] | None = None,
    ) -> Memory:
        """Add a new memory."""
        import uuid

        memory = Memory(
            id=uuid.uuid4().hex[:12],
            content=content,
            category=category,
            source=source,
            created_at=datetime.now(),
            tags=tags or [],
        )

        self.memories[memory.id] = memory
        self._save()
        return memory

    def get(self, memory_id: str) -> Memory | None:
        """Get a memory by ID and increment access count."""
        memory = self.memories.get(memory_id)
        if memory:
            memory.access_count += 1
            memory.last_accessed = datetime.now()
            self._save()
        return memory

    def search(self, query: str, category: str | None = None, limit: int = 10) -> list[Memory]:
        """Search memories by content."""
        query_lower = query.lower()
        matches = []

        for memory in self.memories.values():
            if category and memory.category != category:
                continue

            score = 0
            # Exact match in content
            if query_lower in memory.content.lower():
                score += 10

            # Match in tags
            for tag in memory.tags:
                if query_lower in tag.lower():
                    score += 5

            # Match in category
            if query_lower in memory.category.lower():
                score += 3

            if score > 0:
                matches.append((memory, score))

        # Sort by score, then by access count
        matches.sort(key=lambda x: (-x[1], -x[0].access_count))

        # Update access for returned memories
        for memory, _ in matches[:limit]:
            memory.access_count += 1
            memory.last_accessed = datetime.now()

        self._save()
        return [m for m, _ in matches[:limit]]

    def list_by_category(self, category: str) -> list[Memory]:
        """List all memories in a category."""
        return [m for m in self.memories.values() if m.category == category]

    def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        if memory_id in self.memories:
            del self.memories[memory_id]
            self._save()
            return True
        return False

    def delete_by_pattern(self, pattern: str) -> int:
        """Delete memories matching a content pattern."""
        to_delete = [
            mid for mid, m in self.memories.items() if pattern.lower() in m.content.lower()
        ]
        for mid in to_delete:
            del self.memories[mid]
        if to_delete:
            self._save()
        return len(to_delete)

    def extract_from_conversation(
        self, messages: list[dict[str, Any]], auto_save: bool = True
    ) -> list[Memory]:
        """Extract potential memories from conversation.

        Looks for patterns like:
        - "I prefer..."
        - "My name is..."
        - "The project uses..."
        - "Important: ..."
        """
        extracted = []

        patterns = [
            (r"i (?:prefer|like|want) (.+?)[.!?]", "preference"),
            (r"my (?:name|email|username) is ([^,.]+)", "fact"),
            (r"(?:remember|note|important)[:\s]+(.+?)[.!?]", "fact"),
            (r"this project (?:uses|is|has) (.+?)[.!?]", "project"),
            (r"(?:error|bug|issue)[:\s]+(.+?)[.!?]", "error"),
        ]

        for msg in messages:
            if msg.get("role") != "user":
                continue

            content = str(msg.get("content", ""))

            for pattern, category in patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    memory_content = match.group(1).strip()
                    if len(memory_content) > 10 and len(memory_content) < 500:
                        memory = self.add(
                            content=memory_content,
                            category=category,
                            source="auto-extract",
                            tags=["auto"],
                        )
                        extracted.append(memory)

        return extracted

    def get_context_for_prompt(self, current_prompt: str, max_memories: int = 5) -> str:
        """Get relevant memories to include in a prompt context."""
        relevant = self.search(current_prompt, limit=max_memories)

        if not relevant:
            return ""

        lines = ["Relevant context from previous conversations:"]
        for mem in relevant:
            lines.append(f"- [{mem.category}] {mem.content}")

        return "\n".join(lines)

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        categories = {}
        for m in self.memories.values():
            categories[m.category] = categories.get(m.category, 0) + 1

        return {
            "total_memories": len(self.memories),
            "by_category": categories,
            "most_accessed": sorted(self.memories.values(), key=lambda m: -m.access_count)[:5],
        }
