"""Process-wide PostHog client for the web UI."""

from __future__ import annotations

import atexit
import os
from typing import Any

from posthog import Posthog


posthog_client: Posthog | None = None


def initialize_posthog() -> Posthog | None:
    """Create the shared client, or no-op in production when unconfigured."""
    global posthog_client
    if posthog_client is not None:
        return posthog_client

    token = os.getenv("POSTHOG_PROJECT_TOKEN")
    host = os.getenv("POSTHOG_HOST")
    production = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower() == "production"
    if not token:
        if not production:
            raise RuntimeError(
                "POSTHOG_PROJECT_TOKEN variable required by PostHog is missing or un-configured, "
                "this causes events to be silently missed. This error stops appearing once "
                "POSTHOG_PROJECT_TOKEN is configured"
            )
        return None
    if not host:
        if not production:
            raise RuntimeError(
                "POSTHOG_HOST variable required by PostHog is missing or un-configured, "
                "this causes events to be silently missed. This error stops appearing once "
                "POSTHOG_HOST is configured"
            )
        return None

    posthog_client = Posthog(
        token,
        host=host,
        enable_exception_autocapture=True,
    )
    atexit.register(posthog_client.shutdown)
    return posthog_client


def capture(event: str, properties: dict[str, Any] | None = None) -> None:
    """Capture through the shared client when analytics is configured."""
    if posthog_client is not None:
        posthog_client.capture(event=event, properties=properties or {})


def capture_exception(exception: BaseException) -> None:
    """Capture an exception through the shared client when analytics is configured."""
    if posthog_client is not None:
        posthog_client.capture_exception(exception)
