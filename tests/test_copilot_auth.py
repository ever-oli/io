"""Tests for io_ai.copilot_auth (Hermes-style Copilot token rules + resolution)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from io_ai.auth import AuthStore
from io_ai.copilot_auth import (
    is_classic_pat,
    resolve_copilot_api_key,
    save_copilot_token_to_auth,
    validate_copilot_token,
)


def test_classic_pat_rejected() -> None:
    valid, msg = validate_copilot_token("ghp_abcdefghijklmnop1234")
    assert valid is False
    assert "Classic" in msg
    assert "ghp_" in msg


def test_oauth_token_accepted() -> None:
    valid, msg = validate_copilot_token("gho_abcdefghijklmnop1234")
    assert valid is True


def test_fine_grained_pat_accepted() -> None:
    valid, msg = validate_copilot_token("github_pat_abcdefghijklmnop1234")
    assert valid is True


def test_resolve_skips_classic_pat_in_env_for_next_var(tmp_path: Path) -> None:
    home = tmp_path / "io"
    home.mkdir()
    env = {"COPILOT_GITHUB_TOKEN": "ghp_bad", "GITHUB_TOKEN": "gho_good"}
    store = AuthStore(home=home, env=env)
    assert resolve_copilot_api_key(store) == "gho_good"


def test_resolve_uses_auth_json_when_env_empty(tmp_path: Path) -> None:
    home = tmp_path / "io"
    home.mkdir()
    (home / "auth.json").write_text(
        json.dumps({"copilot": {"api_key": "gho_from_file"}}),
        encoding="utf-8",
    )
    store = AuthStore(home=home, env={})
    assert resolve_copilot_api_key(store) == "gho_from_file"


def test_save_copilot_token_rejects_classic_pat(tmp_path: Path) -> None:
    home = tmp_path / "io"
    home.mkdir()
    store = AuthStore(home=home, env={})
    with pytest.raises(ValueError, match="Classic"):
        save_copilot_token_to_auth(store, "ghp_nope")


def test_save_copilot_token_writes_auth_json(tmp_path: Path) -> None:
    home = tmp_path / "io"
    home.mkdir()
    store = AuthStore(home=home, env={})
    save_copilot_token_to_auth(store, "gho_saved")
    data = json.loads((home / "auth.json").read_text(encoding="utf-8"))
    assert data["copilot"]["api_key"] == "gho_saved"


def test_gh_cli_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "io"
    home.mkdir()
    store = AuthStore(home=home, env={})
    monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with patch("io_ai.copilot_auth._try_gh_cli_token", return_value="gho_from_cli"):
        assert resolve_copilot_api_key(store) == "gho_from_cli"


def test_gh_cli_classic_pat_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "io"
    home.mkdir()
    store = AuthStore(home=home, env={})
    monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with patch("io_ai.copilot_auth._try_gh_cli_token", return_value="ghp_classic"):
        with pytest.raises(ValueError, match="unsupported"):
            resolve_copilot_api_key(store)
