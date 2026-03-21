"""Shell and directory tools."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..config import get_io_home
from ..security.tirith import check_command_security, tirith_approval_suffix


DANGEROUS_SNIPPETS = (
    "rm -rf",
    "git reset --hard",
    "git clean -fd",
    "sudo ",
    "mkfs",
    "dd if=",
)


class BashTool(Tool):
    name = "bash"
    description = "Run a shell command in the current workspace."
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string"},
        },
        "required": ["command"],
    }

    def approval_reason(self, arguments: dict[str, object]) -> str | None:
        command = str(arguments.get("command", ""))
        for snippet in DANGEROUS_SNIPPETS:
            if snippet in command:
                return f"Command requires approval because it matches a dangerous pattern: {snippet}"
        t = tirith_approval_suffix(command, home=get_io_home())
        if t:
            return t
        return None

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        command = str(arguments.get("command", "")).strip()
        if not command:
            return ToolResult(content="No command provided.", is_error=True)
        verdict = check_command_security(command, home=context.home)
        if verdict.get("action") == "block":
            msg = str(verdict.get("summary") or "blocked by Tirith").strip()
            return ToolResult(content=f"Tirith blocked: {msg}" if msg else "Tirith blocked.", is_error=True)
        cwd = Path(str(arguments.get("cwd", context.cwd))).expanduser()
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd),
            env={**os.environ, **context.env},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        cb = context.tool_output_callback
        if cb is not None and process.stdout is not None and process.stderr is not None:

            async def _drain(reader: asyncio.StreamReader, stream_name: str) -> bytes:
                parts: list[bytes] = []
                while True:
                    chunk = await reader.read(4096)
                    if not chunk:
                        break
                    parts.append(chunk)
                    cb("bash", stream_name, chunk.decode("utf-8", errors="replace"))
                return b"".join(parts)

            stdout, stderr = await asyncio.gather(
                _drain(process.stdout, "stdout"),
                _drain(process.stderr, "stderr"),
            )
            await process.wait()
        else:
            stdout, stderr = await process.communicate()
        output = stdout.decode("utf-8", errors="replace")
        error = stderr.decode("utf-8", errors="replace")
        content = output.strip()
        if error.strip():
            content = f"{content}\n{error.strip()}".strip()
        if not content:
            content = f"Command exited with code {process.returncode}."
        return ToolResult(content=content, is_error=process.returncode != 0, metadata={"exit_code": process.returncode})


class LsTool(Tool):
    name = "ls"
    description = "List files in a directory."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
        },
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        path = Path(str(arguments.get("path", context.cwd))).expanduser()
        resolved = path if path.is_absolute() else context.cwd / path
        if not resolved.exists():
            return ToolResult(content=f"Path does not exist: {resolved}", is_error=True)
        entries = sorted(resolved.iterdir(), key=lambda item: item.name)
        lines = []
        for entry in entries:
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{entry.name}{suffix}")
        return ToolResult(content="\n".join(lines))


GLOBAL_TOOL_REGISTRY.register(BashTool())
GLOBAL_TOOL_REGISTRY.register(LsTool())
