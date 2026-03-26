from __future__ import annotations

from io_cli.gateway_models import Platform, PlatformConfig
from io_cli.gateway_platforms.base import BasePlatformAdapter
from io_cli.gateway_runner import ADAPTER_TYPES


def test_gateway_adapter_type_matrix_complete() -> None:
    expected = {
        Platform.TELEGRAM,
        Platform.DISCORD,
        Platform.WHATSAPP,
        Platform.SLACK,
        Platform.SIGNAL,
        Platform.MATTERMOST,
        Platform.MATRIX,
        Platform.HOMEASSISTANT,
        Platform.EMAIL,
        Platform.SMS,
        Platform.DINGTALK,
        Platform.API_SERVER,
        Platform.WEBHOOK,
    }
    assert set(ADAPTER_TYPES) == expected


def test_gateway_adapters_construct_with_platform_config() -> None:
    for platform, adapter_cls in ADAPTER_TYPES.items():
        try:
            adapter = adapter_cls(PlatformConfig(enabled=True))
        except KeyError:
            # Some adapters read required env vars at construction time (e.g. SMS).
            continue
        assert isinstance(adapter, BasePlatformAdapter)
        assert adapter.platform == platform
        assert adapter.running is False

