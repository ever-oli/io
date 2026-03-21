"""NuggetShelf — multi-nugget manager (port of Nuggets `shelf.ts`, MIT)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .memory import Nugget


class NuggetShelf:
    def __init__(self, *, save_dir: Path, auto_save: bool = True) -> None:
        self.save_dir = Path(save_dir)
        self.auto_save = auto_save
        self._nuggets: dict[str, Nugget] = {}

    def create(
        self,
        name: str,
        *,
        d: int = 16384,
        banks: int = 4,
        ensembles: int = 1,
    ) -> Nugget:
        if name in self._nuggets:
            raise ValueError(f"Nugget {name!r} already exists")
        n = Nugget(
            name=name,
            d=d,
            banks=banks,
            ensembles=ensembles,
            auto_save=self.auto_save,
            save_dir=self.save_dir,
        )
        self._nuggets[name] = n
        return n

    def get(self, name: str) -> Nugget:
        if name not in self._nuggets:
            raise ValueError(f"Nugget {name!r} not found")
        return self._nuggets[name]

    def get_or_create(self, name: str) -> Nugget:
        if name in self._nuggets:
            return self._nuggets[name]
        return self.create(name)

    def remove(self, name: str) -> None:
        if name not in self._nuggets:
            raise ValueError(f"Nugget {name!r} not found")
        path = self.save_dir / f"{name}.nugget.json"
        if path.exists():
            path.unlink()
        del self._nuggets[name]

    def list(self) -> list[dict[str, Any]]:
        return [n.status() for n in self._nuggets.values()]

    def remember(self, nugget_name: str, key: str, value: str) -> None:
        self.get(nugget_name).remember(key, value)

    def recall(self, query: str, nugget_name: str | None = None, session_id: str = "") -> dict[str, Any]:
        if nugget_name:
            r = self.get(nugget_name).recall(query, session_id)
            return {**r, "nugget_name": nugget_name}
        best: dict[str, Any] = {
            "answer": None,
            "confidence": 0.0,
            "margin": 0.0,
            "found": False,
            "key": "",
            "nugget_name": None,
        }
        for name, nugget in self._nuggets.items():
            r = nugget.recall(query, session_id)
            if r["found"] and r["confidence"] > best["confidence"]:
                best = {**r, "nugget_name": name}
        return best

    def forget(self, nugget_name: str, key: str) -> bool:
        return self.get(nugget_name).forget(key)

    def load_all(self) -> None:
        if not self.save_dir.exists():
            return
        for path in sorted(self.save_dir.glob("*.nugget.json")):
            try:
                n = Nugget.load(path, auto_save=self.auto_save)
                self._nuggets[n.name] = n
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                continue

    def save_all(self) -> None:
        for n in self._nuggets.values():
            n.save()

    def has(self, name: str) -> bool:
        return name in self._nuggets

    def __len__(self) -> int:
        return len(self._nuggets)
