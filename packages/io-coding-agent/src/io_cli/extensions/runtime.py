"""Extension loading and event dispatch."""

from __future__ import annotations

import importlib.util
import inspect
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from ..config import ensure_io_home


Handler = Callable[[dict[str, Any]], Any]


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass
class ExtensionAPI:
    name: str
    runner: "ExtensionRunner"

    def on(self, event_type: str, handler: Handler | None = None):
        def _register(fn: Handler) -> Handler:
            self.runner.handlers[event_type].append((self.name, fn))
            return fn

        if handler is not None:
            return _register(handler)
        return _register


@dataclass
class ExtensionRunner:
    search_paths: list[Path] = field(default_factory=list)
    handlers: dict[str, list[tuple[str, Handler]]] = field(default_factory=lambda: defaultdict(list))
    loaded: dict[str, ModuleType] = field(default_factory=dict)

    @classmethod
    def default_paths(cls, *, home: Path | None = None, cwd: Path | None = None) -> list[Path]:
        home = ensure_io_home(home)
        paths = [home / "agent" / "extensions"]
        if cwd is not None:
            paths.append(cwd / ".io" / "extensions")
        return paths

    def load_all(self) -> list[str]:
        loaded_names = []
        for directory in self.search_paths:
            if not directory.exists():
                continue
            for file_path in sorted(directory.glob("*.py")):
                if file_path.name.startswith("_"):
                    continue
                name = file_path.stem
                if name in self.loaded:
                    continue
                spec = importlib.util.spec_from_file_location(f"io_extension_{name}", file_path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                api = ExtensionAPI(name=name, runner=self)
                if hasattr(module, "register"):
                    module.register(api)
                self.loaded[name] = module
                loaded_names.append(name)
        return loaded_names

    async def emit(self, event_type: str, payload: dict[str, Any]) -> list[Any]:
        results = []
        for _, handler in self.handlers.get(event_type, []):
            results.append(await _maybe_await(handler(dict(payload))))
        return results

    async def emit_before_agent_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        merged = dict(payload)
        for result in await self.emit("before_agent_start", payload):
            if isinstance(result, dict):
                merged.update(result)
        return merged

    async def emit_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = dict(payload)
        for _, handler in self.handlers.get("context", []):
            result = await _maybe_await(handler(dict(current)))
            if isinstance(result, dict) and "messages" in result:
                current["messages"] = result["messages"]
        return current

    async def emit_tool_call(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = dict(payload)
        for _, handler in self.handlers.get("tool_call", []):
            result = await _maybe_await(handler(dict(current)))
            if isinstance(result, dict):
                if result.get("block"):
                    return {"block": True, "reason": result.get("reason", "blocked")}
                current.update(result)
        return current

    async def emit_tool_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = dict(payload)
        for _, handler in self.handlers.get("tool_result", []):
            result = await _maybe_await(handler(dict(current)))
            if isinstance(result, dict):
                current.update(result)
        return current
