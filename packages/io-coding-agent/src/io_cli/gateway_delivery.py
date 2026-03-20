"""Delivery routing for gateway and cron outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .gateway_models import GatewayConfig, Platform
from .gateway_platforms import BasePlatformAdapter
from .gateway_session import SessionSource


MAX_PLATFORM_OUTPUT = 4000
TRUNCATED_VISIBLE = 3800


@dataclass(slots=True)
class DeliveryTarget:
    platform: Platform
    chat_id: str | None = None
    thread_id: str | None = None
    is_origin: bool = False
    is_explicit: bool = False

    @classmethod
    def parse(cls, target: str, origin: SessionSource | None = None) -> "DeliveryTarget":
        normalized = str(target or "").strip().lower()
        if normalized == "origin":
            if origin is not None:
                return cls(
                    platform=origin.platform,
                    chat_id=origin.chat_id,
                    thread_id=origin.thread_id,
                    is_origin=True,
                )
            return cls(platform=Platform.LOCAL, is_origin=True)
        if normalized == "local":
            return cls(platform=Platform.LOCAL)
        if ":" in normalized:
            platform_name, chat_id = normalized.split(":", 1)
            try:
                return cls(
                    platform=Platform(platform_name),
                    chat_id=chat_id,
                    is_explicit=True,
                )
            except ValueError:
                return cls(platform=Platform.LOCAL)
        try:
            return cls(platform=Platform(normalized))
        except ValueError:
            return cls(platform=Platform.LOCAL)

    def to_string(self) -> str:
        if self.is_origin:
            return "origin"
        if self.platform == Platform.LOCAL:
            return "local"
        if self.chat_id:
            return f"{self.platform.value}:{self.chat_id}"
        return self.platform.value


class DeliveryRouter:
    def __init__(
        self,
        *,
        home: Path,
        config: GatewayConfig,
        adapters: dict[Platform, BasePlatformAdapter] | None = None,
    ) -> None:
        self.home = home
        self.config = config
        self.adapters = adapters if adapters is not None else {}
        self.output_dir = home / "cron" / "output"

    def resolve_targets(
        self,
        deliver: str | list[str],
        *,
        origin: SessionSource | None = None,
    ) -> list[DeliveryTarget]:
        items = [deliver] if isinstance(deliver, str) else list(deliver)
        resolved: list[DeliveryTarget] = []
        seen: set[tuple[str, str | None, str | None]] = set()
        for item in items:
            target = DeliveryTarget.parse(str(item), origin=origin)
            if target.chat_id is None and target.platform != Platform.LOCAL:
                home_channel = self.config.get_home_channel(target.platform)
                if home_channel is None:
                    continue
                target.chat_id = home_channel.chat_id
            key = (target.platform.value, target.chat_id, target.thread_id)
            if key in seen:
                continue
            seen.add(key)
            resolved.append(target)
        if self.config.always_log_local and ("local", None, None) not in seen:
            resolved.append(DeliveryTarget(platform=Platform.LOCAL))
        return resolved

    async def deliver(
        self,
        content: str,
        targets: list[DeliveryTarget],
        *,
        job_id: str | None = None,
        job_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        existing_local_path: str | None = None,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for target in targets:
            try:
                if target.platform == Platform.LOCAL:
                    payload = self._deliver_local(
                        content,
                        job_id=job_id,
                        job_name=job_name,
                        metadata=metadata,
                        existing_local_path=existing_local_path,
                    )
                else:
                    payload = await self._deliver_platform(
                        target,
                        content,
                        metadata=metadata,
                    )
                results[target.to_string()] = {"success": True, "result": payload}
            except Exception as exc:
                results[target.to_string()] = {"success": False, "error": str(exc)}
        return results

    def _deliver_local(
        self,
        content: str,
        *,
        job_id: str | None = None,
        job_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        existing_local_path: str | None = None,
    ) -> dict[str, Any]:
        if existing_local_path:
            return {"path": existing_local_path, "reused": True}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.output_dir / (job_id or "misc")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{timestamp}.md"
        lines = [f"# {job_name or 'Delivery Output'}", ""]
        lines.append(f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if job_id:
            lines.append(f"**Job ID:** {job_id}")
        if metadata:
            for key, value in metadata.items():
                lines.append(f"**{key}:** {value}")
        lines.extend(["", "---", "", content])
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return {"path": str(output_path), "timestamp": timestamp}

    async def _deliver_platform(
        self,
        target: DeliveryTarget,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        adapter = self.adapters.get(target.platform)
        if adapter is None:
            raise RuntimeError(f"No adapter registered for platform '{target.platform.value}'.")
        payload = content
        if len(payload) > MAX_PLATFORM_OUTPUT:
            payload = payload[:TRUNCATED_VISIBLE].rstrip() + "\n\n[Output truncated]"
        return await adapter.send_message(
            target.chat_id or "",
            payload,
            thread_id=target.thread_id,
            metadata=metadata,
        )
