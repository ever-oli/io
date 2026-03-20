"""Tests for io_cli.acp_adapter.auth."""

from io_cli.acp_adapter.auth import detect_provider, has_provider


class TestHasProvider:
    def test_has_provider_with_resolved_runtime(self, monkeypatch):
        monkeypatch.setattr(
            "io_cli.acp_adapter.auth.resolve_runtime_provider",
            lambda **kwargs: {"provider": "openrouter", "api_key": "sk-or-test"},
        )
        assert has_provider() is True

    def test_has_no_provider_when_runtime_has_no_key(self, monkeypatch):
        monkeypatch.setattr(
            "io_cli.acp_adapter.auth.resolve_runtime_provider",
            lambda **kwargs: {"provider": "openrouter", "api_key": ""},
        )
        assert has_provider() is False

    def test_has_no_provider_when_runtime_resolution_fails(self, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("no provider")

        monkeypatch.setattr("io_cli.acp_adapter.auth.resolve_runtime_provider", _boom)
        assert has_provider() is False


class TestDetectProvider:
    def test_detect_openrouter(self, monkeypatch):
        monkeypatch.setattr(
            "io_cli.acp_adapter.auth.resolve_runtime_provider",
            lambda **kwargs: {"provider": "openrouter", "api_key": "sk-or-test"},
        )
        assert detect_provider() == "openrouter"

    def test_detect_anthropic(self, monkeypatch):
        monkeypatch.setattr(
            "io_cli.acp_adapter.auth.resolve_runtime_provider",
            lambda **kwargs: {"provider": "anthropic", "api_key": "sk-ant-test"},
        )
        assert detect_provider() == "anthropic"

    def test_detect_none_when_no_key(self, monkeypatch):
        monkeypatch.setattr(
            "io_cli.acp_adapter.auth.resolve_runtime_provider",
            lambda **kwargs: {"provider": "kimi-coding", "api_key": ""},
        )
        assert detect_provider() is None

    def test_detect_none_on_resolution_error(self, monkeypatch):
        def _boom(**kwargs):
            raise RuntimeError("broken")

        monkeypatch.setattr("io_cli.acp_adapter.auth.resolve_runtime_provider", _boom)
        assert detect_provider() is None
