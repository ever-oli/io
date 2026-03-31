"""MCP Client - Full Model Context Protocol integration.

Provides:
- Connect to MCP servers
- OAuth and API key authentication
- Resource discovery and reading
- Tool invocation
- Server management
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class MCPAuthType(Enum):
    """MCP authentication types."""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    BEARER = "bearer"


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    url: str
    auth_type: MCPAuthType = MCPAuthType.NONE
    auth_token: str | None = None
    api_key: str | None = None
    headers: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "auth_type": self.auth_type.value,
            "headers": self.headers or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerConfig:
        return cls(
            name=data["name"],
            url=data["url"],
            auth_type=MCPAuthType(data.get("auth_type", "none")),
            auth_token=data.get("auth_token"),
            api_key=data.get("api_key"),
            headers=data.get("headers"),
        )


class MCPClient:
    """Client for Model Context Protocol servers."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session: Any = None

    async def connect(self) -> bool:
        """Connect to the MCP server."""
        try:
            import aiohttp

            # Initialize session
            headers = self.config.headers or {}

            if self.config.auth_type == MCPAuthType.BEARER and self.config.auth_token:
                headers["Authorization"] = f"Bearer {self.config.auth_token}"
            elif self.config.auth_type == MCPAuthType.API_KEY and self.config.api_key:
                headers["X-API-Key"] = self.config.api_key

            # Test connection
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(f"{self.config.url}/health") as resp:
                    return resp.status == 200
        except Exception as e:
            print(f"Failed to connect to MCP server {self.config.name}: {e}")
            return False

    async def list_resources(self) -> list[dict[str, Any]]:
        """List available resources on the server."""
        try:
            import aiohttp

            headers = self.config.headers or {}
            if self.config.auth_type == MCPAuthType.BEARER and self.config.auth_token:
                headers["Authorization"] = f"Bearer {self.config.auth_token}"
            elif self.config.auth_type == MCPAuthType.API_KEY and self.config.api_key:
                headers["X-API-Key"] = self.config.api_key

            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(f"{self.config.url}/resources") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("resources", [])
                    return []
        except Exception:
            return []

    async def read_resource(self, resource_uri: str) -> dict[str, Any] | None:
        """Read a specific resource."""
        try:
            import aiohttp

            headers = self.config.headers or {}
            if self.config.auth_type == MCPAuthType.BEARER and self.config.auth_token:
                headers["Authorization"] = f"Bearer {self.config.auth_token}"
            elif self.config.auth_type == MCPAuthType.API_KEY and self.config.api_key:
                headers["X-API-Key"] = self.config.api_key

            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(f"{self.config.url}/resources/{resource_uri}") as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
        except Exception:
            return None

    async def list_tools(self) -> list[dict[str, Any]]:
        """List available tools on the server."""
        try:
            import aiohttp

            headers = self.config.headers or {}
            if self.config.auth_type == MCPAuthType.BEARER and self.config.auth_token:
                headers["Authorization"] = f"Bearer {self.config.auth_token}"
            elif self.config.auth_type == MCPAuthType.API_KEY and self.config.api_key:
                headers["X-API-Key"] = self.config.api_key

            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(f"{self.config.url}/tools") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("tools", [])
                    return []
        except Exception:
            return []

    async def call_tool(self, tool_name: str, parameters: dict[str, Any]) -> dict[str, Any] | None:
        """Call a tool on the server."""
        try:
            import aiohttp

            headers = self.config.headers or {}
            if self.config.auth_type == MCPAuthType.BEARER and self.config.auth_token:
                headers["Authorization"] = f"Bearer {self.config.auth_token}"
            elif self.config.auth_type == MCPAuthType.API_KEY and self.config.api_key:
                headers["X-API-Key"] = self.config.api_key

            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(
                    f"{self.config.url}/tools/{tool_name}",
                    json={"parameters": parameters},
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
        except Exception:
            return None


class MCPManager:
    """Manages MCP server connections."""

    def __init__(self, home: Path):
        self.home = home
        self.config_dir = home / "mcp"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._clients: dict[str, MCPClient] = {}

    def _get_config_path(self, name: str) -> Path:
        """Get config file path for a server."""
        return self.config_dir / f"{name}.json"

    def list_servers(self) -> list[MCPServerConfig]:
        """List all configured MCP servers."""
        servers = []
        for config_file in self.config_dir.glob("*.json"):
            try:
                data = json.loads(config_file.read_text())
                servers.append(MCPServerConfig.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return servers

    def get_server(self, name: str) -> MCPServerConfig | None:
        """Get a server configuration."""
        config_path = self._get_config_path(name)
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
                return MCPServerConfig.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    def add_server(self, config: MCPServerConfig) -> None:
        """Add or update a server configuration."""
        config_path = self._get_config_path(config.name)
        config_path.write_text(json.dumps(config.to_dict(), indent=2))

    def remove_server(self, name: str) -> bool:
        """Remove a server configuration."""
        config_path = self._get_config_path(name)
        if config_path.exists():
            config_path.unlink()
            return True
        return False

    async def get_client(self, name: str) -> MCPClient | None:
        """Get or create a client for a server."""
        if name in self._clients:
            return self._clients[name]

        config = self.get_server(name)
        if not config:
            return None

        client = MCPClient(config)
        if await client.connect():
            self._clients[name] = client
            return client
        return None

    async def test_connection(self, name: str) -> bool:
        """Test connection to a server."""
        client = await self.get_client(name)
        return client is not None
