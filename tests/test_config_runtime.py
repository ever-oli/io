from __future__ import annotations

from pathlib import Path

from io_cli.config import (
    ensure_io_home,
    get_config_value,
    load_config,
    load_soul,
    save_config,
    set_config_value,
    soul_status_payload,
)


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


def test_load_soul_prefers_repo_soul_md(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "iohome_soul")
    (home / "SOUL.md").write_text("from_io_home", encoding="utf-8")
    ws = tmp_path / "workspace_repo"
    ws.mkdir()
    (ws / "soul.md").write_text("from_workspace", encoding="utf-8")
    assert load_soul(home=home, cwd=ws) == "from_workspace"


def test_load_soul_falls_back_to_io_home(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "iohome_soul2")
    (home / "SOUL.md").write_text("only_default_home", encoding="utf-8")
    ws = tmp_path / "workspace_no_soul"
    ws.mkdir()
    assert load_soul(home=home, cwd=ws) == "only_default_home"


def test_soul_status_payload_shows_preview(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "iohome_status")
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "soul.md").write_text("# Hello\nsecond line\n", encoding="utf-8")
    cfg = load_config(home)
    cfg.setdefault("soul", {})["workspace_root"] = str(repo)
    save_config(cfg, home)
    p = soul_status_payload(home=home, cwd=tmp_path / "nowhere")
    assert p["soul_source"] == "workspace_root"
    assert "Hello" in p["preview"]
    assert p["exists"] is True


def test_load_soul_workspace_root_for_gateway_style_cwd(tmp_path: Path) -> None:
    """Telegram gateway uses terminal.cwd default → $HOME; soul.workspace_root pins repo soul."""
    home = ensure_io_home(tmp_path / "iohome_soul3")
    (home / "SOUL.md").write_text("io_home_fallback", encoding="utf-8")
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / "soul.md").write_text("from_workspace_root_config", encoding="utf-8")
    fake_home_cwd = tmp_path / "simulated_user_home"
    fake_home_cwd.mkdir()
    cfg = load_config(home)
    cfg.setdefault("soul", {})["workspace_root"] = str(repo)
    assert load_soul(home=home, cwd=fake_home_cwd, config=cfg) == "from_workspace_root_config"


def test_terminal_config_includes_phase_two_backend_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "home")

    assert config["terminal"]["singularity_image"]
    assert config["terminal"]["modal_image"]
    assert config["terminal"]["daytona_image"]
