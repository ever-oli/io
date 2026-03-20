from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_io_home(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setenv("IO_HOME", str(tmp_path / ".io"))
