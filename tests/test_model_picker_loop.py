"""Model picker must not nest asyncio.run when REPL uses asyncio.run for slash commands."""

from __future__ import annotations

import asyncio

from io_cli.model_picker import _prompt_toolkit_in_thread


def test_nested_loop_detection_off_main() -> None:
    assert _prompt_toolkit_in_thread() is False


def test_nested_loop_detection_inside_asyncio_run() -> None:
    seen: list[bool] = []

    async def _probe() -> None:
        seen.append(_prompt_toolkit_in_thread())

    asyncio.run(_probe())
    assert seen == [True]
