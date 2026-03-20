"""Pod lifecycle scaffold."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field


@dataclass(slots=True)
class PodSpec:
    name: str
    gpu: str = "A10G"
    replicas: int = 1


@dataclass
class PodLifecycle:
    pods: dict[str, PodSpec] = field(default_factory=dict)

    def create(self, spec: PodSpec) -> PodSpec:
        self.pods[spec.name] = spec
        return spec

    def list(self) -> list[PodSpec]:
        return [self.pods[name] for name in sorted(self.pods)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="io-pods", description="IO pod lifecycle scaffold")
    parser.add_argument("name", nargs="?", default="demo-pod")
    args = parser.parse_args(argv)
    lifecycle = PodLifecycle()
    spec = lifecycle.create(PodSpec(name=args.name))
    print(f"Created pod {spec.name} ({spec.gpu}, replicas={spec.replicas})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

