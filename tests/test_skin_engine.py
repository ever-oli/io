from __future__ import annotations

from io_cli.banner import build_welcome_banner
from io_cli.skin_engine import SkinEngine, get_active_skin
from rich.console import Console
from rich.panel import Panel


def test_builtin_skin_loads_default_theme() -> None:
    theme = SkinEngine().load()
    assert theme.prompt_symbol
    assert theme.labels["assistant"]


def test_banner_builder_returns_panel() -> None:
    panel = build_welcome_banner(Console(), model="mock/io-test", cwd=".", enabled_toolsets=["io-cli"])
    assert isinstance(panel, Panel)


def test_active_skin_has_io_branding() -> None:
    skin = get_active_skin()
    assert "IO" in skin.get_branding("agent_name", "IO")
