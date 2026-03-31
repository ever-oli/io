"""MCP Tools - Tools for Model Context Protocol integration.

Provides agent-accessible tools for:
- Connecting to MCP servers
- Listing resources and tools
- Reading resources
- Calling MCP tools
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from io_agent import Tool, ToolContext, ToolResult

from ..mcp_client import MCPAuthType, MCPManager, MCPServerConfig


class MCPConnectTool(Tool):
    """Connect to an MCP server."""

    name = "mcp_connect"
    description = "Connect to an MCP (Model Context Protocol) server. Supports OAuth, API keys, and bearer token authentication."

    async def execute(
        self,
        name: str,
        url: str,
        auth_type: str = "none",
        auth_token: str | None = None,
        api_key: str | None = None,
        context: ToolContext | None = None,
    ) -> ToolResult:
        """Connect to an MCP server.

        Args:
            name: Name for this server connection
            url: MCP server URL
            auth_type: Authentication type (none, api_key, oauth, bearer)
            auth_token: OAuth/Bearer token (if applicable)
            api_key: API key (if applicable)
            context: Tool execution context
        """
        home = Path.home() / ".io"
        manager = MCPManager(home)

        config = MCPServerConfig(
            name=name,
            url=url,
            auth_type=MCPAuthType(auth_type),
            auth_token=auth_token,
            api_key=api_key,
        )

        # Test connection
        connected = await manager.test_connection(name)

        if connected:
            manager.add_server(config)
            return ToolResult(
                content=f"✅ Connected to MCP server: {name} at {url}",
                data={"name": name, "url": url, "status": "connected"},
            )
        else:
            return ToolResult(
                content=f"⚠️ Could not connect to MCP server at {url}. Configuration saved for retry.",
                data={"name": name, "url": url, "status": "pending"},
            )


class MCPListTool(Tool):
    """List MCP resources or tools."""

    name = "mcp_list"
    description = "List resources or tools from a connected MCP server."

    async def execute(
        self,
        server: str,
        list_type: str = "resources",
        context: ToolContext | None = None,
    ) -> ToolResult:
        """List MCP resources or tools.

        Args:
            server: MCP server name
            list_type: What to list (resources, tools, servers)
            context: Tool execution context
        """
        home = Path.home() / ".io"
        manager = MCPManager(home)

        if list_type == "servers":
            servers = manager.list_servers()
            if not servers:
                return ToolResult(content="📂 No MCP servers configured")

            lines = [f"🔗 MCP Servers ({len(servers)}):"]
            for s in servers:
                lines.append(f"  • {s.name}: {s.url}")

            return ToolResult(content="\n".join(lines))

        client = await manager.get_client(server)
        if not client:
            return ToolResult(
                content=f"❌ Not connected to MCP server: {server}",
                is_error=True,
            )

        if list_type == "resources":
            resources = await client.list_resources()
            if not resources:
                return ToolResult(content=f"📂 No resources available on {server}")

            lines = [f"📚 MCP Resources on {server} ({len(resources)}):"]
            for r in resources:
                lines.append(f"  • {r.get('uri', 'unknown')}: {r.get('name', 'unnamed')}")

            return ToolResult(
                content="\n".join(lines),
                data={"resources": resources},
            )

        elif list_type == "tools":
            tools = await client.list_tools()
            if not tools:
                return ToolResult(content=f"🔧 No tools available on {server}")

            lines = [f"🔧 MCP Tools on {server} ({len(tools)}):"]
            for t in tools:
                lines.append(
                    f"  • {t.get('name', 'unknown')}: {t.get('description', 'No description')}"
                )

            return ToolResult(
                content="\n".join(lines),
                data={"tools": tools},
            )

        else:
            return ToolResult(content=f"❌ Unknown list_type: {list_type}", is_error=True)


class MCPReadTool(Tool):
    """Read an MCP resource."""

    name = "mcp_read"
    description = "Read a resource from an MCP server."

    async def execute(
        self,
        server: str,
        resource_uri: str,
        context: ToolContext | None = None,
    ) -> ToolResult:
        """Read an MCP resource.

        Args:
            server: MCP server name
            resource_uri: URI of the resource to read
            context: Tool execution context
        """
        home = Path.home() / ".io"
        manager = MCPManager(home)

        client = await manager.get_client(server)
        if not client:
            return ToolResult(
                content=f"❌ Not connected to MCP server: {server}",
                is_error=True,
            )

        resource = await client.read_resource(resource_uri)
        if resource is None:
            return ToolResult(
                content=f"❌ Resource not found: {resource_uri}",
                is_error=True,
            )

        content = resource.get("content", "")
        mime_type = resource.get("mimeType", "unknown")

        return ToolResult(
            content=f"📄 Resource: {resource_uri}\nType: {mime_type}\n\n{content[:2000]}",
            data=resource,
        )


class MCPCallTool(Tool):
    """Call an MCP tool."""

    name = "mcp_call"
    description = "Call a tool on an MCP server with parameters."

    async def execute(
        self,
        server: str,
        tool_name: str,
        parameters: dict[str, Any] | None = None,
        context: ToolContext | None = None,
    ) -> ToolResult:
        """Call an MCP tool.

        Args:
            server: MCP server name
            tool_name: Name of the tool to call
            parameters: Tool parameters
            context: Tool execution context
        """
        home = Path.home() / ".io"
        manager = MCPManager(home)

        client = await manager.get_client(server)
        if not client:
            return ToolResult(
                content=f"❌ Not connected to MCP server: {server}",
                is_error=True,
            )

        result = await client.call_tool(tool_name, parameters or {})
        if result is None:
            return ToolResult(
                content=f"❌ Tool call failed: {tool_name}",
                is_error=True,
            )

        return ToolResult(
            content=f"✅ Tool executed: {tool_name}\n\nResult: {json.dumps(result, indent=2)[:1500]}",
            data=result,
        )


import json
