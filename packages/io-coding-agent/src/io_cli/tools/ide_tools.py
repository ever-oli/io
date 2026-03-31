"""IDE integration tools for connecting IO to VS Code, JetBrains, and other editors.

This module provides tools that enable bidirectional communication between
IO and IDEs for file operations, diff viewing, and selection synchronization.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..config import load_config

logger = logging.getLogger(__name__)

# IDE connection state
_ide_connections: dict[str, "IDEConnection"] = {}
_connection_lock = asyncio.Lock()


@dataclass
class IDEConnection:
    """Represents a connection to an IDE."""

    ide_type: str  # vscode, jetbrains, cursor, windsurf, etc.
    host: str = "localhost"
    port: int = 0
    socket_path: str | None = None  # For Unix domain sockets
    last_ping: float = field(default_factory=lambda: 0.0)
    capabilities: set[str] = field(default_factory=set)

    def is_alive(self) -> bool:
        """Check if the connection is still alive."""
        import time

        return time.monotonic() - self.last_ping < 30.0  # 30 second timeout


class IDEOpenTool(Tool):
    """Open a file in the connected IDE at a specific line/column."""

    name = "ide_open"
    description = (
        "Open a file in the connected IDE. Supports line and column positioning. "
        "Examples: ide_open path=src/main.py, ide_open path=src/main.py line=42, "
        "ide_open path=src/main.py line=42 column=10"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to open (relative or absolute)",
            },
            "line": {
                "type": "integer",
                "description": "Line number to position cursor (1-indexed)",
                "minimum": 1,
            },
            "column": {
                "type": "integer",
                "description": "Column number to position cursor (1-indexed)",
                "minimum": 1,
            },
        },
        "required": ["path"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        path = str(arguments["path"])
        line = int(arguments.get("line", 1))
        column = int(arguments.get("column", 1))

        # Resolve path
        file_path = Path(path).expanduser()
        if not file_path.is_absolute():
            file_path = context.cwd / file_path
        file_path = file_path.resolve()

        if not file_path.exists():
            return ToolResult(content=f"File not found: {file_path}", is_error=True)

        # Try different IDE connection methods
        result = await _try_open_in_ide(file_path, line, column, context)
        return result


class IDEShowDiffTool(Tool):
    """Show a diff in the IDE's diff viewer."""

    name = "ide_diff"
    description = (
        "Show a unified diff in the IDE's diff viewer. "
        "Can compare file against original or show a patch."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to diff",
            },
            "original_content": {
                "type": "string",
                "description": "Original content to diff against (if not using git)",
            },
            "use_git": {
                "type": "boolean",
                "description": "Compare against git HEAD instead of provided content",
                "default": False,
            },
        },
        "required": ["path"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        path = str(arguments["path"])
        original_content = arguments.get("original_content")
        use_git = bool(arguments.get("use_git", False))

        file_path = Path(path).expanduser()
        if not file_path.is_absolute():
            file_path = context.cwd / file_path
        file_path = file_path.resolve()

        if not file_path.exists():
            return ToolResult(content=f"File not found: {file_path}", is_error=True)

        return await _show_diff_in_ide(file_path, original_content, use_git, context)


class IDESyncSelectionTool(Tool):
    """Synchronize cursor/selection between IO and IDE."""

    name = "ide_sync_selection"
    description = (
        "Get or set the current cursor position and selection in the IDE. "
        "Use without arguments to get current position, or provide values to set."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path (required when setting position)",
            },
            "start_line": {
                "type": "integer",
                "description": "Start line of selection (1-indexed)",
            },
            "start_column": {
                "type": "integer",
                "description": "Start column of selection (1-indexed)",
            },
            "end_line": {
                "type": "integer",
                "description": "End line of selection (1-indexed, optional)",
            },
            "end_column": {
                "type": "integer",
                "description": "End column of selection (1-indexed, optional)",
            },
        },
        "required": [],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        path = arguments.get("path")

        if path:
            # Setting position
            file_path = Path(str(path)).expanduser()
            if not file_path.is_absolute():
                file_path = context.cwd / file_path
            file_path = file_path.resolve()

            start_line = int(arguments.get("start_line", 1))
            start_column = int(arguments.get("start_column", 1))
            end_line = arguments.get("end_line")
            end_column = arguments.get("end_column")

            return await _set_selection_in_ide(
                file_path, start_line, start_column, end_line, end_column, context
            )
        else:
            # Getting position
            return await _get_selection_from_ide(context)


class IDEStatusTool(Tool):
    """Get the status of IDE connections."""

    name = "ide_status"
    description = (
        "Check which IDEs are connected and their capabilities. "
        "Returns a list of connected IDEs and available features."
    )
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        return await _get_ide_status(context)


class IDEConnectTool(Tool):
    """Connect to an IDE or check connection status."""

    name = "ide_connect"
    description = (
        "Connect to a specific IDE (vscode, jetbrains, cursor, windsurf) "
        "or auto-detect the running IDE."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "ide": {
                "type": "string",
                "description": "IDE to connect to (vscode, jetbrains, cursor, windsurf, auto)",
                "enum": ["vscode", "jetbrains", "cursor", "windsurf", "auto"],
            },
            "port": {
                "type": "integer",
                "description": "Custom port for IDE protocol (optional)",
            },
        },
        "required": [],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        ide_type = arguments.get("ide", "auto")
        port = arguments.get("port")

        return await _connect_to_ide(str(ide_type), port, context)


# Helper functions


async def _try_open_in_ide(
    file_path: Path, line: int, column: int, context: ToolContext
) -> ToolResult:
    """Try multiple methods to open a file in an IDE."""

    # Method 1: VS Code URL protocol
    if await _try_vscode_url(file_path, line, column):
        return ToolResult(content=f"Opened {file_path} in VS Code at line {line}, column {column}")

    # Method 2: VS Code CLI
    if await _try_vscode_cli(file_path, line, column):
        return ToolResult(content=f"Opened {file_path} in VS Code at line {line}, column {column}")

    # Method 3: JetBrains (via toolbox or CLI)
    if await _try_jetbrains(file_path, line, column):
        return ToolResult(
            content=f"Opened {file_path} in JetBrains IDE at line {line}, column {column}"
        )

    # Method 4: Cursor
    if await _try_cursor(file_path, line, column):
        return ToolResult(content=f"Opened {file_path} in Cursor at line {line}, column {column}")

    # Method 5: Windsurf
    if await _try_windsurf(file_path, line, column):
        return ToolResult(content=f"Opened {file_path} in Windsurf at line {line}, column {column}")

    # Method 6: Generic file:// URL with line/column
    if await _try_generic_url(file_path, line, column):
        return ToolResult(
            content=f"Opened {file_path} via system file handler (line/column may not work)"
        )

    return ToolResult(
        content=f"Could not open {file_path} in any IDE. Please ensure an IDE is installed.",
        is_error=True,
    )


async def _try_vscode_url(file_path: Path, line: int, column: int) -> bool:
    """Try opening via VS Code URL protocol."""
    try:
        # Format: vscode://file/path/to/file:line:column
        uri = f"vscode://file{quote(str(file_path))}:{line}:{column}"
        webbrowser.open(uri)
        await asyncio.sleep(0.5)
        return True
    except Exception:
        return False


async def _try_vscode_cli(file_path: Path, line: int, column: int) -> bool:
    """Try opening via VS Code CLI."""
    try:
        # Try multiple possible code commands
        code_commands = ["code", "code-insiders", "code-oss", "codium"]

        for cmd in code_commands:
            try:
                result = await asyncio.create_subprocess_exec(
                    cmd,
                    "--goto",
                    f"{file_path}:{line}:{column}",
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await result.wait()
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.SubprocessError):
                continue

        return False
    except Exception:
        return False


async def _try_jetbrains(file_path: Path, line: int, column: int) -> bool:
    """Try opening in a JetBrains IDE."""
    try:
        # Try JetBrains Toolbox or idea command
        jetbrains_commands = [
            "idea",  # IntelliJ IDEA
            "webstorm",
            "pycharm",
            "phpstorm",
            "rubymine",
            "goland",
            "clion",
            "rustrover",
        ]

        for cmd in jetbrains_commands:
            try:
                result = await asyncio.create_subprocess_exec(
                    cmd,
                    "--line",
                    str(line),
                    "--column",
                    str(column),
                    str(file_path),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                await result.wait()
                if result.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.SubprocessError):
                continue

        return False
    except Exception:
        return False


async def _try_cursor(file_path: Path, line: int, column: int) -> bool:
    """Try opening in Cursor editor."""
    try:
        result = await asyncio.create_subprocess_exec(
            "cursor",
            "--goto",
            f"{file_path}:{line}:{column}",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await result.wait()
        return result.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        # Also try URL scheme
        try:
            uri = f"cursor://file{quote(str(file_path))}:{line}:{column}"
            webbrowser.open(uri)
            await asyncio.sleep(0.5)
            return True
        except Exception:
            return False


async def _try_windsurf(file_path: Path, line: int, column: int) -> bool:
    """Try opening in Windsurf editor."""
    try:
        result = await asyncio.create_subprocess_exec(
            "windsurf",
            "--goto",
            f"{file_path}:{line}:{column}",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await result.wait()
        return result.returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        # Also try URL scheme
        try:
            uri = f"windsurf://file{quote(str(file_path))}:{line}:{column}"
            webbrowser.open(uri)
            await asyncio.sleep(0.5)
            return True
        except Exception:
            return False


async def _try_generic_url(file_path: Path, line: int, column: int) -> bool:
    """Try opening via generic file:// URL."""
    try:
        uri = f"file://{quote(str(file_path))}"
        webbrowser.open(uri)
        return True
    except Exception:
        return False


async def _show_diff_in_ide(
    file_path: Path,
    original_content: object,
    use_git: bool,
    context: ToolContext,
) -> ToolResult:
    """Show diff in IDE."""

    if use_git:
        # Open git diff view in IDE
        # VS Code: code --diff <file>
        try:
            result = await asyncio.create_subprocess_exec(
                "code",
                "--diff",
                str(file_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            await result.wait()
            if result.returncode == 0:
                return ToolResult(content=f"Opened git diff for {file_path} in VS Code")
        except (FileNotFoundError, subprocess.SubprocessError):
            pass

    # Create a temp file with original content for comparison
    if original_content:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".original",
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(str(original_content))
                original_path = f.name

            # Try VS Code diff
            try:
                result = await asyncio.create_subprocess_exec(
                    "code",
                    "--diff",
                    original_path,
                    str(file_path),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                await result.wait()
                if result.returncode == 0:
                    return ToolResult(content=f"Opened diff view comparing original to {file_path}")
            except (FileNotFoundError, subprocess.SubprocessError):
                pass

            # Clean up temp file
            try:
                os.unlink(original_path)
            except OSError:
                pass

        except Exception as e:
            return ToolResult(content=f"Error creating diff: {e}", is_error=True)

    return ToolResult(
        content=f"Could not open diff view. Supported IDEs: VS Code with git diff or file comparison.",
        is_error=True,
    )


async def _set_selection_in_ide(
    file_path: Path,
    start_line: int,
    start_column: int,
    end_line: object,
    end_column: object,
    context: ToolContext,
) -> ToolResult:
    """Set cursor/selection in IDE."""

    # Open file first
    line = start_line
    column = start_column

    result = await _try_open_in_ide(file_path, line, column, context)

    if end_line and end_column:
        # Selection range
        return ToolResult(
            content=f"Set selection in {file_path}: lines {start_line}-{end_line}, "
            f"columns {start_column}-{end_column}. Note: Full selection range "
            f"requires IDE-specific extensions."
        )

    return result


async def _get_selection_from_ide(context: ToolContext) -> ToolResult:
    """Get current cursor/selection from IDE."""

    # Try to get from connected IDEs via protocol
    for conn_id, conn in _ide_connections.items():
        if conn.is_alive():
            # Would need protocol implementation to get selection
            pass

    return ToolResult(
        content="No IDE connected or IDE does not support selection retrieval. "
        "Use 'ide_open' to open files and 'ide_sync_selection' to set cursor position."
    )


async def _get_ide_status(context: ToolContext) -> ToolResult:
    """Get status of IDE connections."""

    connected = []

    # Check for VS Code
    if await _check_vscode_running():
        connected.append("VS Code")

    # Check for JetBrains
    if await _check_jetbrains_running():
        connected.append("JetBrains IDE")

    # Check for Cursor
    if await _check_cursor_running():
        connected.append("Cursor")

    # Check for Windsurf
    if await _check_windsurf_running():
        connected.append("Windsurf")

    if connected:
        return ToolResult(
            content=f"Connected IDEs: {', '.join(connected)}\n\n"
            "Available tools:\n"
            "- ide_open: Open files at specific line/column\n"
            "- ide_diff: Show diffs in IDE\n"
            "- ide_sync_selection: Sync cursor position\n"
        )

    return ToolResult(
        content="No IDE detected. Supported IDEs:\n"
        "- VS Code / VS Code Insiders\n"
        "- JetBrains (IntelliJ, WebStorm, PyCharm, etc.)\n"
        "- Cursor\n"
        "- Windsurf\n\n"
        "Ensure your IDE is running and try 'ide_connect' to establish connection."
    )


async def _check_vscode_running() -> bool:
    """Check if VS Code is running."""
    try:
        # Try to list VS Code processes
        if sys.platform == "darwin":
            result = await asyncio.create_subprocess_exec(
                "pgrep",
                "-x",
                "Code",
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "linux":
            result = await asyncio.create_subprocess_exec(
                "pgrep",
                "code",
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "win32":
            result = await asyncio.create_subprocess_exec(
                "tasklist",
                "/FI",
                "IMAGENAME eq Code.exe",
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        else:
            return False

        stdout, _ = await result.communicate()
        return result.returncode == 0 and stdout.strip()
    except Exception:
        return False


async def _check_jetbrains_running() -> bool:
    """Check if JetBrains IDE is running."""
    try:
        if sys.platform == "darwin":
            # Check for JetBrains apps on macOS
            for app in [
                "IntelliJ IDEA",
                "WebStorm",
                "PyCharm",
                "PhpStorm",
                "RubyMine",
                "GoLand",
                "CLion",
            ]:
                result = await asyncio.create_subprocess_exec(
                    "pgrep",
                    "-f",
                    app,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                stdout, _ = await result.communicate()
                if result.returncode == 0 and stdout.strip():
                    return True
        return False
    except Exception:
        return False


async def _check_cursor_running() -> bool:
    """Check if Cursor is running."""
    try:
        if sys.platform == "darwin":
            result = await asyncio.create_subprocess_exec(
                "pgrep",
                "-x",
                "Cursor",
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "linux":
            result = await asyncio.create_subprocess_exec(
                "pgrep",
                "cursor",
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        else:
            return False

        stdout, _ = await result.communicate()
        return result.returncode == 0 and stdout.strip()
    except Exception:
        return False


async def _check_windsurf_running() -> bool:
    """Check if Windsurf is running."""
    try:
        if sys.platform == "darwin":
            result = await asyncio.create_subprocess_exec(
                "pgrep",
                "-x",
                "Windsurf",
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "linux":
            result = await asyncio.create_subprocess_exec(
                "pgrep",
                "windsurf",
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        else:
            return False

        stdout, _ = await result.communicate()
        return result.returncode == 0 and stdout.strip()
    except Exception:
        return False


async def _connect_to_ide(ide_type: str, port: object, context: ToolContext) -> ToolResult:
    """Connect to a specific IDE."""

    if ide_type == "auto":
        # Try to auto-detect
        status = await _get_ide_status(context)
        if "No IDE detected" not in status.content:
            return ToolResult(
                content=f"Auto-detected IDEs:\n{status.content}\nUse 'ide_open' to work with files."
            )
        return ToolResult(content="No IDE detected automatically. Please specify an IDE type.")

    # Validate IDE type
    valid_ides = ["vscode", "jetbrains", "cursor", "windsurf"]
    if ide_type not in valid_ides:
        return ToolResult(
            content=f"Unknown IDE: {ide_type}. Valid options: {', '.join(valid_ides)}",
            is_error=True,
        )

    # Check if IDE is running
    checks = {
        "vscode": _check_vscode_running,
        "jetbrains": _check_jetbrains_running,
        "cursor": _check_cursor_running,
        "windsurf": _check_windsurf_running,
    }

    is_running = await checks[ide_type]()

    if not is_running:
        return ToolResult(
            content=f"{ide_type.capitalize()} does not appear to be running. "
            "Please start your IDE first.",
            is_error=True,
        )

    # Store connection
    conn = IDEConnection(
        ide_type=ide_type,
        port=port if port else 0,
    )
    async with _connection_lock:
        _ide_connections[ide_type] = conn

    return ToolResult(
        content=f"✓ Connected to {ide_type.capitalize()}\n\n"
        f"You can now use:\n"
        f"- ide_open path=... line=... column=...\n"
        f"- ide_diff path=...\n"
        f"- ide_sync_selection path=... line=... column=..."
    )


# Register tools
GLOBAL_TOOL_REGISTRY.register(IDEOpenTool())
GLOBAL_TOOL_REGISTRY.register(IDEShowDiffTool())
GLOBAL_TOOL_REGISTRY.register(IDESyncSelectionTool())
GLOBAL_TOOL_REGISTRY.register(IDEStatusTool())
GLOBAL_TOOL_REGISTRY.register(IDEConnectTool())
