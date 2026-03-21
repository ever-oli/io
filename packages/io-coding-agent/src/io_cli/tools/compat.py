"""IO-compatible tool aliases backed by IO's local tool implementations."""

from __future__ import annotations

import asyncio
import json
import re
from difflib import unified_diff
from pathlib import Path

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..config import get_io_home
from ..environments import EnvironmentConfigurationError, create_environment, resolve_terminal_environment
from ..security.tirith import check_command_security, tirith_approval_suffix
from .process_runtime import process_registry
from .shell import DANGEROUS_SNIPPETS


def _resolve(context: ToolContext, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (context.cwd / path).resolve()


def _json(payload: dict[str, object]) -> ToolResult:
    return ToolResult(content=json.dumps(payload, ensure_ascii=False))


class TerminalCompatTool(Tool):
    name = "terminal"
    description = (
        "Execute shell commands with optional background process support. "
        "IO-compatible terminal backend for IO."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to execute on the VM"},
            "backend": {
                "type": "string",
                "enum": ["local", "docker", "ssh", "singularity", "modal", "daytona"],
                "description": "Optional backend override. Defaults to terminal.backend in ~/.io/config.yaml.",
            },
            "background": {
                "type": "boolean",
                "description": "Only for servers/watchers that never exit.",
                "default": False,
            },
            "timeout": {
                "type": "integer",
                "description": "Max seconds to wait before timing out foreground commands.",
                "minimum": 1,
            },
            "workdir": {
                "type": "string",
                "description": "Working directory for this command.",
            },
            "check_interval": {
                "type": "integer",
                "description": "Reserved for IO gateway parity.",
                "minimum": 30,
            },
            "pty": {
                "type": "boolean",
                "description": "Reserved for IO PTY parity.",
                "default": False,
            },
            "docker_image": {
                "type": "string",
                "description": "Optional Docker image override when backend=docker.",
            },
            "docker_mount_cwd_to_workspace": {
                "type": "boolean",
                "description": "Mount the host working directory into /workspace for Docker commands.",
            },
            "singularity_image": {
                "type": "string",
                "description": "Optional Singularity or Apptainer image override when backend=singularity.",
            },
            "modal_image": {
                "type": "string",
                "description": "Optional Modal image override when backend=modal.",
            },
            "daytona_image": {
                "type": "string",
                "description": "Optional Daytona image override when backend=daytona.",
            },
            "container_cpu": {
                "type": "integer",
                "description": "CPU allocation override for remote/container backends.",
                "minimum": 0,
            },
            "container_memory": {
                "type": "integer",
                "description": "Memory allocation override in MB for remote/container backends.",
                "minimum": 0,
            },
            "container_disk": {
                "type": "integer",
                "description": "Disk allocation override in MB for remote/container backends.",
                "minimum": 0,
            },
            "container_persistent": {
                "type": "boolean",
                "description": "Keep filesystem state between backend sessions when supported.",
            },
            "ssh_host": {
                "type": "string",
                "description": "SSH hostname override when backend=ssh.",
            },
            "ssh_user": {
                "type": "string",
                "description": "SSH username override when backend=ssh.",
            },
            "ssh_port": {
                "type": "integer",
                "description": "SSH port override when backend=ssh.",
                "minimum": 1,
            },
            "ssh_key": {
                "type": "string",
                "description": "SSH key path override when backend=ssh.",
            },
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
            return ToolResult(
                content=json.dumps(
                    {"error": (f"Tirith blocked: {msg}" if msg else "Tirith blocked.")},
                    ensure_ascii=False,
                ),
                is_error=True,
            )

        background = bool(arguments.get("background", False))
        task_id = str(context.metadata.get("task_id", "") or "")
        try:
            request = resolve_terminal_environment(
                home=context.home,
                cwd=context.cwd,
                arguments=arguments,
            )
            environment = create_environment(request, env=context.env)
        except EnvironmentConfigurationError as exc:
            return ToolResult(content=json.dumps({"error": str(exc)}), is_error=True)
        except Exception as exc:
            return ToolResult(
                content=json.dumps({"error": f"Failed to resolve terminal backend: {exc}"}),
                is_error=True,
            )

        execution_cwd: Path | str
        reported_cwd: str
        if request.backend in {"modal", "daytona"}:
            execution_cwd = request.remote_cwd
            reported_cwd = request.remote_cwd
        else:
            execution_cwd = request.workdir
            reported_cwd = str(request.workdir)

        if background:
            try:
                session = environment.spawn_background(
                    registry=process_registry,
                    command=command,
                    cwd=execution_cwd,
                    task_id=task_id,
                )
            except EnvironmentConfigurationError as exc:
                return ToolResult(content=json.dumps({"error": str(exc)}), is_error=True)
            except Exception as exc:
                return ToolResult(
                    content=json.dumps({"error": f"Failed to start background process: {exc}"}),
                    is_error=True,
                )
            return _json(
                {
                    "session_id": session.id,
                    "command": command,
                    "cwd": reported_cwd,
                    "backend": request.backend,
                    "background": True,
                    "output": "Background process started",
                }
            )

        stream_cb = None
        if context.tool_output_callback is not None:
            out_cb = context.tool_output_callback

            def stream_cb(stream_name: str, chunk: str) -> None:
                out_cb("terminal", stream_name, chunk)

        try:
            result = await asyncio.to_thread(
                environment.execute,
                command,
                cwd=execution_cwd,
                timeout=request.timeout,
                stream_callback=stream_cb,
            )
        except EnvironmentConfigurationError as exc:
            return ToolResult(content=json.dumps({"error": str(exc)}), is_error=True)
        except Exception as exc:
            return ToolResult(
                content=json.dumps({"error": f"Terminal backend execution failed: {exc}"}),
                is_error=True,
            )
        finally:
            try:
                environment.cleanup()
            except Exception:
                pass
        return _json(
            {
                "command": command,
                "cwd": reported_cwd,
                "backend": request.backend,
                "output": str(result.get("output", "")),
                "exit_code": result.get("returncode"),
                "timed_out": bool(result.get("timed_out", False)),
            }
        )


class ProcessCompatTool(Tool):
    name = "process"
    description = (
        "Manage background processes started with terminal(background=true). "
        "Actions: list, poll, log, wait, kill, write, submit."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "poll", "log", "wait", "kill", "write", "submit"],
            },
            "session_id": {"type": "string"},
            "data": {"type": "string"},
            "timeout": {"type": "integer", "minimum": 1},
            "offset": {"type": "integer"},
            "limit": {"type": "integer", "minimum": 1},
        },
        "required": ["action"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        action = str(arguments.get("action", "") or "")
        session_id = str(arguments.get("session_id", "") or "")
        task_id = str(context.metadata.get("task_id", "") or "")

        if action == "list":
            return _json({"processes": process_registry.list_sessions(task_id=task_id or None)})
        if not session_id:
            return ToolResult(content=json.dumps({"error": f"session_id is required for {action}"}), is_error=True)
        if action == "poll":
            return _json(process_registry.poll(session_id))
        if action == "log":
            return _json(
                process_registry.read_log(
                    session_id,
                    offset=int(arguments.get("offset", 0) or 0),
                    limit=int(arguments.get("limit", 200) or 200),
                )
            )
        if action == "wait":
            timeout = arguments.get("timeout")
            timeout_value = int(timeout) if timeout is not None else None
            return _json(process_registry.wait(session_id, timeout=timeout_value))
        if action == "kill":
            return _json(process_registry.kill_process(session_id))
        if action == "write":
            return _json(process_registry.write_stdin(session_id, str(arguments.get("data", ""))))
        if action == "submit":
            return _json(process_registry.submit_stdin(session_id, str(arguments.get("data", ""))))
        return ToolResult(
            content=json.dumps(
                {"error": f"Unknown process action: {action}. Use: list, poll, log, wait, kill, write, submit"}
            ),
            is_error=True,
        )


class ReadFileCompatTool(Tool):
    name = "read_file"
    description = (
        "Read a text file with line numbers and pagination. IO-compatible alias for IO file reads."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "default": 1, "minimum": 1},
            "limit": {"type": "integer", "default": 500, "maximum": 2000},
        },
        "required": ["path"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        path = _resolve(context, str(arguments.get("path", "")))
        if not path.exists():
            return ToolResult(content=json.dumps({"error": f"File not found: {path}"}), is_error=True)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ToolResult(content=json.dumps({"error": f"File is not UTF-8 text: {path}"}), is_error=True)
        lines = text.splitlines()
        offset = max(1, int(arguments.get("offset", 1) or 1))
        limit = min(2000, max(1, int(arguments.get("limit", 500) or 500)))
        chunk = lines[offset - 1 : offset - 1 + limit]
        numbered = "\n".join(f"{index}|{line}" for index, line in enumerate(chunk, start=offset))
        return _json(
            {
                "path": str(path),
                "offset": offset,
                "limit": limit,
                "total_lines": len(lines),
                "content": numbered,
            }
        )


class WriteFileCompatTool(Tool):
    name = "write_file"
    description = "Write content to a file, replacing existing content."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        path = _resolve(context, str(arguments.get("path", "")))
        content = str(arguments.get("content", ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return _json({"path": str(path), "bytes_written": len(content.encode("utf-8")), "success": True})


class PatchCompatTool(Tool):
    name = "patch"
    description = (
        "Targeted find-and-replace edits. Supports IO replace mode and returns a unified diff."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["replace", "patch"], "default": "replace"},
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean", "default": False},
            "patch": {"type": "string"},
        },
        "required": ["mode"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        mode = str(arguments.get("mode", "replace") or "replace")
        if mode == "patch":
            return ToolResult(
                content=json.dumps(
                    {
                        "error": (
                            "V4A patch mode is not wired into IO yet. Use mode='replace' with path/old_string/new_string."
                        )
                    }
                ),
                is_error=True,
            )

        path_value = arguments.get("path")
        old_string = arguments.get("old_string")
        new_string = arguments.get("new_string")
        if not all(isinstance(item, str) and item for item in (path_value, old_string)) or new_string is None:
            return ToolResult(
                content=json.dumps({"error": "replace mode requires path, old_string, and new_string"}),
                is_error=True,
            )

        path = _resolve(context, str(path_value))
        if not path.exists():
            return ToolResult(content=json.dumps({"error": f"File not found: {path}"}), is_error=True)

        original = path.read_text(encoding="utf-8")
        if str(old_string) not in original:
            return ToolResult(
                content=json.dumps({"error": "old_string not found in file"}),
                is_error=True,
            )

        replace_all = bool(arguments.get("replace_all", False))
        count = original.count(str(old_string)) if replace_all else 1
        updated = original.replace(str(old_string), str(new_string), 0 if replace_all else 1)
        path.write_text(updated, encoding="utf-8")

        diff = "".join(
            unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=str(path),
                tofile=str(path),
            )
        )
        return _json({"path": str(path), "replacements": count, "diff": diff, "success": True})


class SearchFilesCompatTool(Tool):
    name = "search_files"
    description = (
        "Search file contents or find files by name. IO-compatible alias for grep/find style operations."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "target": {"type": "string", "enum": ["content", "files"], "default": "content"},
            "path": {"type": "string", "default": "."},
            "file_glob": {"type": "string"},
            "limit": {"type": "integer", "default": 50},
            "offset": {"type": "integer", "default": 0},
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_only", "count"],
                "default": "content",
            },
            "context": {"type": "integer", "default": 0},
        },
        "required": ["pattern"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        pattern = str(arguments.get("pattern", "") or "")
        target = str(arguments.get("target", "content") or "content")
        root = _resolve(context, str(arguments.get("path", ".")))
        limit = max(1, int(arguments.get("limit", 50) or 50))
        offset = max(0, int(arguments.get("offset", 0) or 0))
        file_glob = str(arguments.get("file_glob", "") or "").strip()
        output_mode = str(arguments.get("output_mode", "content") or "content")
        context_lines = max(0, int(arguments.get("context", 0) or 0))

        if target == "files":
            paths = [path for path in root.rglob("*") if path.is_file() and path.match(pattern)]
            paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
            results = [str(path) for path in paths[offset : offset + limit]]
            return _json({"target": "files", "matches": results, "count": len(results)})

        try:
            regex = re.compile(pattern)
        except re.error:
            regex = re.compile(re.escape(pattern))

        matches: list[str] = []
        counts: dict[str, int] = {}
        files_only: list[str] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if file_glob and not path.match(file_glob):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            file_match_count = 0
            for index, line in enumerate(lines, start=1):
                if not regex.search(line):
                    continue
                file_match_count += 1
                if output_mode == "content":
                    if context_lines:
                        start = max(1, index - context_lines)
                        end = min(len(lines), index + context_lines)
                        block = "\n".join(
                            f"{path}:{line_no}:{lines[line_no - 1]}" for line_no in range(start, end + 1)
                        )
                        matches.append(block)
                    else:
                        matches.append(f"{path}:{index}:{line}")
            if file_match_count:
                counts[str(path)] = file_match_count
                files_only.append(str(path))

        if output_mode == "files_only":
            payload_matches = list(dict.fromkeys(files_only))[offset : offset + limit]
        elif output_mode == "count":
            items = list(counts.items())[offset : offset + limit]
            payload_matches = [f"{path}:{count}" for path, count in items]
        else:
            payload_matches = matches[offset : offset + limit]

        return _json({"target": "content", "matches": payload_matches, "count": len(payload_matches)})


GLOBAL_TOOL_REGISTRY.register(TerminalCompatTool())
GLOBAL_TOOL_REGISTRY.register(ProcessCompatTool())
GLOBAL_TOOL_REGISTRY.register(ReadFileCompatTool())
GLOBAL_TOOL_REGISTRY.register(WriteFileCompatTool())
GLOBAL_TOOL_REGISTRY.register(PatchCompatTool())
GLOBAL_TOOL_REGISTRY.register(SearchFilesCompatTool())
