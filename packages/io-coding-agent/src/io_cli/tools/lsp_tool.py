"""LSPTool - Language Server Protocol integration for IDE features.

Provides:
- Symbol navigation (go to definition, find references)
- Type information and hover
- Symbol search across codebase
- Workspace symbols
- Code actions

This is a foundational implementation. Full LSP support requires:
1. LSP client connection to language servers
2. Server lifecycle management
3. Incremental sync
4. Full protocol implementation

For now, we provide the tool interface and basic symbol extraction.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from io_agent import Tool, ToolContext, ToolResult


@dataclass
class SymbolInfo:
    """Information about a code symbol."""

    name: str
    kind: str  # function, class, variable, etc.
    file_path: str
    line: int
    column: int
    documentation: str = ""
    signature: str = ""


class LSPTool(Tool):
    """Language Server Protocol integration tool.

    Provides IDE-like features:
    - Find symbol definitions
    - Find symbol references
    - Search workspace symbols
    - Get type information
    """

    name = "lsp"
    description = """Use Language Server Protocol features for code navigation and analysis.

This tool provides IDE-like capabilities:
- Find where a symbol is defined (go to definition)
- Find all references to a symbol
- Search for symbols across the workspace
- Get type information and documentation

Use this when you need to:
1. Understand unfamiliar code by navigating to definitions
2. Find all usages of a function or class
3. Explore the structure of a large codebase
4. Get type information for better code understanding
"""

    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["definition", "references", "symbol_search", "workspace_symbol", "hover"],
                "description": "LSP action to perform",
            },
            "file_path": {
                "type": "string",
                "description": "Path to the file (for definition, references, hover)",
            },
            "line": {
                "type": "integer",
                "description": "Line number (0-indexed for definition, references, hover)",
            },
            "column": {
                "type": "integer",
                "description": "Column number (0-indexed for definition, references, hover)",
            },
            "symbol_name": {
                "type": "string",
                "description": "Symbol name to search for (for symbol_search, workspace_symbol)",
            },
            "language": {
                "type": "string",
                "description": "Language for workspace-wide symbol search (python, typescript, etc.)",
            },
        },
        "required": ["action"],
    }

    def __init__(self):
        self._lsp_servers: dict[str, Any] = {}  # Language -> LSP server process

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        return None  # LSP operations are safe

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        try:
            action = arguments["action"]

            if action == "definition":
                return await self._find_definition(context, arguments)
            elif action == "references":
                return await self._find_references(context, arguments)
            elif action == "symbol_search":
                return await self._symbol_search(context, arguments)
            elif action == "workspace_symbol":
                return await self._workspace_symbol(context, arguments)
            elif action == "hover":
                return await self._hover(context, arguments)
            else:
                return ToolResult(content=f"Unknown action: {action}", is_error=True)

        except Exception as e:
            return ToolResult(content=f"LSP error: {e}", is_error=True)

    async def _find_definition(self, context: ToolContext, args: dict) -> ToolResult:
        """Find where a symbol is defined."""
        file_path = args.get("file_path")
        line = args.get("line", 0)
        column = args.get("column", 0)

        if not file_path:
            return ToolResult(content="file_path required for definition lookup", is_error=True)

        # Placeholder implementation
        # In full implementation, this would:
        # 1. Start/connect to appropriate LSP server
        # 2. Send textDocument/definition request
        # 3. Parse response and return locations

        content = f"""[LSP Definition Placeholder]

Would find definition for symbol at:
  File: {file_path}
  Line: {line}
  Column: {column}

Full implementation requires:
1. LSP server connection ({self._detect_language(file_path)})
2. textDocument/definition request
3. Response parsing

For now, consider using grep to find definitions:
  grep -r "def symbol_name" --include="*.py"
"""

        return ToolResult(content=content)

    async def _find_references(self, context: ToolContext, args: dict) -> ToolResult:
        """Find all references to a symbol."""
        file_path = args.get("file_path")
        line = args.get("line", 0)
        column = args.get("column", 0)

        if not file_path:
            return ToolResult(content="file_path required for references lookup", is_error=True)

        content = f"""[LSP References Placeholder]

Would find all references to symbol at:
  File: {file_path}
  Line: {line}
  Column: {column}

Full implementation requires:
1. LSP server connection ({self._detect_language(file_path)})
2. textDocument/references request
3. Response parsing

For now, consider using grep:
  grep -r "symbol_name" --include="*.py"
"""

        return ToolResult(content=content)

    async def _symbol_search(self, context: ToolContext, args: dict) -> ToolResult:
        """Search for symbols in a specific file."""
        file_path = args.get("file_path")
        symbol_name = args.get("symbol_name")

        if not file_path or not symbol_name:
            return ToolResult(content="file_path and symbol_name required", is_error=True)

        # Extract symbols using ctags or similar as fallback
        symbols = await self._extract_symbols_fallback(file_path)

        matching = [s for s in symbols if symbol_name.lower() in s.name.lower()]

        if not matching:
            return ToolResult(content=f"No symbols matching '{symbol_name}' found in {file_path}")

        content_lines = [f"Symbols matching '{symbol_name}' in {file_path}:", ""]
        for sym in matching:
            content_lines.append(f"  {sym.kind}: {sym.name} (line {sym.line})")
            if sym.documentation:
                content_lines.append(f"    {sym.documentation[:100]}...")

        return ToolResult(content="\n".join(content_lines))

    async def _workspace_symbol(self, context: ToolContext, args: dict) -> ToolResult:
        """Search for symbols across the entire workspace."""
        symbol_name = args.get("symbol_name")
        language = args.get("language")

        if not symbol_name:
            return ToolResult(content="symbol_name required for workspace search", is_error=True)

        content = f"""[LSP Workspace Symbol Placeholder]

Would search workspace for: {symbol_name}
Language filter: {language or "all"}

Full implementation requires:
1. LSP server connection
2. workspace/symbol request
3. Response parsing

For now, consider using grep across the codebase:
  grep -r "{symbol_name}" --include="*.{language or "py"}" {context.cwd}
"""

        return ToolResult(content=content)

    async def _hover(self, context: ToolContext, args: dict) -> ToolResult:
        """Get hover information (type, docs) for a symbol."""
        file_path = args.get("file_path")
        line = args.get("line", 0)
        column = args.get("column", 0)

        if not file_path:
            return ToolResult(content="file_path required for hover", is_error=True)

        content = f"""[LSP Hover Placeholder]

Would get hover info for symbol at:
  File: {file_path}
  Line: {line}
  Column: {column}

Full implementation requires:
1. LSP server connection ({self._detect_language(file_path)})
2. textDocument/hover request
3. Response parsing
"""

        return ToolResult(content=content)

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".rb": "ruby",
        }
        return mapping.get(ext, "unknown")

    async def _extract_symbols_fallback(self, file_path: str) -> list[SymbolInfo]:
        """Extract symbols using ctags or regex as LSP fallback."""
        symbols = []
        path = Path(file_path)

        if not path.exists():
            return symbols

        try:
            content = path.read_text()
            lines = content.split("\n")

            language = self._detect_language(file_path)

            if language == "python":
                # Simple regex-based extraction for Python
                import re

                for i, line in enumerate(lines, 1):
                    # Class definitions
                    match = re.match(r"^class\s+(\w+)", line)
                    if match:
                        symbols.append(
                            SymbolInfo(
                                name=match.group(1),
                                kind="class",
                                file_path=file_path,
                                line=i,
                                column=line.find(match.group(1)),
                            )
                        )

                    # Function definitions
                    match = re.match(r"^(?:async\s+)?def\s+(\w+)", line)
                    if match:
                        symbols.append(
                            SymbolInfo(
                                name=match.group(1),
                                kind="function",
                                file_path=file_path,
                                line=i,
                                column=line.find(match.group(1)),
                            )
                        )

            elif language in ["javascript", "typescript"]:
                import re

                for i, line in enumerate(lines, 1):
                    # Functions
                    match = re.match(r"^(?:async\s+)?(?:function\s+)?(\w+)\s*[=\(]", line)
                    if match:
                        symbols.append(
                            SymbolInfo(
                                name=match.group(1),
                                kind="function",
                                file_path=file_path,
                                line=i,
                                column=line.find(match.group(1)),
                            )
                        )

                    # Classes
                    match = re.match(r"^class\s+(\w+)", line)
                    if match:
                        symbols.append(
                            SymbolInfo(
                                name=match.group(1),
                                kind="class",
                                file_path=file_path,
                                line=i,
                                column=line.find(match.group(1)),
                            )
                        )

        except Exception:
            pass

        return symbols


class LSPDiagnosticsTool(Tool):
    """Get diagnostics (errors, warnings) from LSP."""

    name = "lsp_diagnostics"
    description = "Get code diagnostics (errors, warnings) from Language Server"

    input_schema = {
        "type": "object",
        "properties": {"file_path": {"type": "string", "description": "Path to file to check"}},
        "required": ["file_path"],
    }

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        return None

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        file_path = arguments.get("file_path")

        content = f"""[LSP Diagnostics Placeholder]

Would get diagnostics for: {file_path}

Full implementation requires LSP server connection.
"""

        return ToolResult(content=content)


# Export LSP tools
LSP_TOOLS = [
    LSPTool(),
    LSPDiagnosticsTool(),
]
