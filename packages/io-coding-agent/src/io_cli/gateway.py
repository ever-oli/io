"""Deferred gateway management surface."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class GatewayManager:
    enabled: bool = False

    def status(self) -> str:
        return "Gateway support is deferred in v1."

