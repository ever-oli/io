"""Local pod lifecycle manager for IO pods."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _pods_home(home: Path | None = None) -> Path:
    root = home or Path(os.getenv("IO_HOME", Path.home() / ".io"))
    path = root / "pods"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class PodSpec:
    name: str
    gpu: str = "A10G"
    replicas: int = 1
    image: str = "vllm/vllm-openai:latest"
    provider: str = "local"
    created_at: str = field(default_factory=_timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PodLifecycle:
    home: Path | None = None
    pods: dict[str, PodSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load()

    @property
    def registry_path(self) -> Path:
        return _pods_home(self.home) / "registry.json"

    def _load(self) -> None:
        if not self.registry_path.exists():
            return
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return
        for name, item in payload.items():
            if not isinstance(item, dict):
                continue
            self.pods[str(name)] = PodSpec(
                name=str(item.get("name") or name),
                gpu=str(item.get("gpu") or "A10G"),
                replicas=int(item.get("replicas") or 1),
                image=str(item.get("image") or "vllm/vllm-openai:latest"),
                provider=str(item.get("provider") or "local"),
                created_at=str(item.get("created_at") or _timestamp()),
                metadata=item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {},
            )

    def _save(self) -> None:
        payload = {
            name: {
                "name": spec.name,
                "gpu": spec.gpu,
                "replicas": spec.replicas,
                "image": spec.image,
                "provider": spec.provider,
                "created_at": spec.created_at,
                "metadata": dict(spec.metadata),
            }
            for name, spec in sorted(self.pods.items())
        }
        self.registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def create(self, spec: PodSpec) -> PodSpec:
        self.pods[spec.name] = spec
        self._save()
        return spec

    def list(self) -> list[PodSpec]:
        return [self.pods[name] for name in sorted(self.pods)]

    def get(self, name: str) -> PodSpec | None:
        return self.pods.get(name)

    def scale(self, name: str, replicas: int) -> PodSpec:
        spec = self.pods[name]
        spec.replicas = max(1, int(replicas))
        self._save()
        return spec

    def delete(self, name: str) -> bool:
        removed = self.pods.pop(name, None)
        if removed is None:
            return False
        self._save()
        return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="io-pods", description="IO pod lifecycle manager")
    parser.add_argument("name", nargs="?", default="demo-pod")
    parser.add_argument("--gpu", default="A10G")
    parser.add_argument("--replicas", type=int, default=1)
    parser.add_argument("--image", default="vllm/vllm-openai:latest")
    parser.add_argument("--provider", default="local")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--delete", action="store_true")
    parser.add_argument("--scale", type=int, default=None)
    args = parser.parse_args(argv)
    lifecycle = PodLifecycle()
    if args.list:
        for spec in lifecycle.list():
            print(f"{spec.name}\t{spec.provider}\t{spec.gpu}\t{spec.replicas}\t{spec.image}")
        return 0
    if args.delete:
        removed = lifecycle.delete(args.name)
        print(f"Deleted pod {args.name}" if removed else f"Pod {args.name} does not exist")
        return 0 if removed else 1
    if args.scale is not None:
        spec = lifecycle.scale(args.name, args.scale)
        print(f"Scaled pod {spec.name} to {spec.replicas} replica(s)")
        return 0
    if args.inspect:
        spec = lifecycle.get(args.name)
        if spec is None:
            print(f"Pod {args.name} does not exist")
            return 1
        print(
            json.dumps(
                {
                    "name": spec.name,
                    "gpu": spec.gpu,
                    "replicas": spec.replicas,
                    "image": spec.image,
                    "provider": spec.provider,
                    "created_at": spec.created_at,
                    "metadata": dict(spec.metadata),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    spec = lifecycle.create(
        PodSpec(
            name=args.name,
            gpu=args.gpu,
            replicas=args.replicas,
            image=args.image,
            provider=args.provider,
        )
    )
    print(f"Created pod {spec.name} ({spec.provider}, {spec.gpu}, replicas={spec.replicas})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
