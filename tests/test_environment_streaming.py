from __future__ import annotations

from pathlib import Path

from io_cli.environments.local import LocalEnvironment


def test_local_execute_streams_lines(tmp_path: Path) -> None:
    env = LocalEnvironment(timeout=30, env={})
    chunks: list[tuple[str, str]] = []

    def cb(stream: str, chunk: str) -> None:
        chunks.append((stream, chunk))

    result = env.execute("echo hello && echo err >&2", cwd=tmp_path, stream_callback=cb)
    assert result.get("returncode") == 0
    streams = {name for name, _ in chunks}
    assert "stdout" in streams
    assert "stderr" in streams
    merged = "".join(part for _, part in chunks)
    assert "hello" in merged
