from __future__ import annotations

from pathlib import Path

from io_cli.config import ensure_io_home, get_config_value, load_config, set_config_value


def test_ensure_io_home_creates_phase_two_layout(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "home")
    expected = [
        home / "cron",
        home / "logs",
        home / "memories",
        home / "skills",
        home / "skins",
        home / "gateway",
        home / "pairing",
        home / "sandboxes",
        home / "agent" / "sessions",
        home / "agent" / "extensions",
    ]
    for path in expected:
        assert path.exists()


def test_config_dot_path_helpers_round_trip(tmp_path: Path) -> None:
    config = load_config(tmp_path / "home")
    set_config_value(config, "display.streaming", True)
    assert get_config_value(config, "display.streaming") is True


def test_terminal_config_includes_phase_two_backend_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "home")

    assert config["terminal"]["singularity_image"]
    assert config["terminal"]["modal_image"]
    assert config["terminal"]["daytona_image"]
