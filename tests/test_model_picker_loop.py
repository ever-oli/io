"""Model picker must not nest asyncio.run when REPL uses asyncio.run for slash commands."""

from __future__ import annotations

import asyncio

from io_ai.types import ModelRef
from prompt_toolkit.document import Document

from io_cli.model_picker import _prompt_toolkit_in_thread
from io_cli.model_picker import _AuthModelCompleter


def test_nested_loop_detection_off_main() -> None:
    assert _prompt_toolkit_in_thread() is False


def test_nested_loop_detection_inside_asyncio_run() -> None:
    seen: list[bool] = []

    async def _probe() -> None:
        seen.append(_prompt_toolkit_in_thread())

    asyncio.run(_probe())
    assert seen == [True]


def test_model_picker_hides_redundant_meta_column() -> None:
    completer = _AuthModelCompleter(
        [
            ModelRef(
                id="copilot/claude-haiku-4.5",
                provider="copilot",
                api="responses",
                remote_id="claude-haiku-4.5",
            )
        ]
    )

    [completion] = list(completer.get_completions(Document(""), None))
    assert completion.display_text == "copilot/claude-haiku-4.5"
    assert completion.display_meta_text == ""


def test_model_picker_shows_friendly_hint_inline() -> None:
    completer = _AuthModelCompleter(
        [
            ModelRef(
                id="openrouter/nvidia/nemotron-3-super-120b-a12b:free",
                provider="openrouter",
                api="responses",
                remote_id="nvidia/nemotron-3-super-120b-a12b:free",
                label="OpenRouter nvidia/nemotron-3-super-120b-a12b:free",
                metadata={"hint": "free"},
            )
        ]
    )

    [completion] = list(completer.get_completions(Document(""), None))
    assert completion.display_text == "openrouter/nvidia/nemotron-3-super-120b-a12b:free · Free"
    assert completion.display_meta_text == ""


def test_model_picker_truncates_without_meta_column() -> None:
    completer = _AuthModelCompleter(
        [
            ModelRef(
                id="anthropic/super-long-claude-model-name-for-truncation-testing-2026-03-31",
                provider="anthropic",
                api="responses",
                remote_id="super-long-claude-model-name-for-truncation-testing-2026-03-31",
            )
        ]
    )

    [completion] = list(completer.get_completions(Document(""), None))
    assert completion.display_text.endswith("…")
    assert completion.display_meta_text == ""
