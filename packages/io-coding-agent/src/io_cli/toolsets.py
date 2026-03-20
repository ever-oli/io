"""IO-style toolset definitions for the IO CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from io_agent import ToolRegistry, ToolsetResolver


PLATFORMS: dict[str, str] = {
    "cli": "CLI",
    "telegram": "Telegram",
    "discord": "Discord",
    "slack": "Slack",
    "whatsapp": "WhatsApp",
    "signal": "Signal",
    "email": "Email",
    "sms": "SMS",
    "homeassistant": "Home Assistant",
    "dingtalk": "DingTalk",
}

_IO_CORE_TOOLS = [
    "web_search",
    "web_extract",
    "terminal",
    "process",
    "read_file",
    "write_file",
    "patch",
    "search_files",
    "memory",
    "session_search",
    "bash",
    "ls",
    "read",
    "write",
    "edit",
    "find",
    "grep",
    "skills_list",
    "skill_view",
    "skill_manage",
    "cronjob",
]

_TOOLSETS: dict[str, dict[str, Any]] = {
    "web": {
        "description": "Web research and content extraction tools",
        "tools": ["web_search", "web_extract"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "search": {
        "description": "Web search only",
        "tools": ["web_search"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "vision": {
        "description": "Image analysis and vision tools",
        "tools": ["vision_analyze"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "image_gen": {
        "description": "Creative generation tools (images)",
        "tools": ["image_generate"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "terminal": {
        "description": "Terminal execution and background process management",
        "tools": ["terminal", "process", "bash", "ls"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "moa": {
        "description": "Advanced reasoning and problem-solving tools",
        "tools": ["mixture_of_agents"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "skills": {
        "description": "Access and manage skill documents",
        "tools": ["skills_list", "skill_view", "skill_manage"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "browser": {
        "description": "Browser automation with web search",
        "tools": [
            "browser_navigate",
            "browser_snapshot",
            "browser_click",
            "browser_type",
            "browser_scroll",
            "browser_back",
            "browser_press",
            "browser_close",
            "browser_get_images",
            "browser_vision",
            "browser_console",
            "web_search",
        ],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "cronjob": {
        "description": "Scheduled task management",
        "tools": ["cronjob"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "messaging": {
        "description": "Cross-platform messaging",
        "tools": ["send_message"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "rl": {
        "description": "RL training and environment control",
        "tools": [
            "rl_list_environments",
            "rl_select_environment",
            "rl_get_current_config",
            "rl_edit_config",
            "rl_start_training",
            "rl_check_status",
            "rl_stop_training",
            "rl_get_results",
            "rl_list_runs",
            "rl_test_inference",
        ],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "file": {
        "description": "File manipulation tools",
        "tools": ["read_file", "write_file", "patch", "search_files", "read", "write", "edit", "find", "grep"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "tts": {
        "description": "Text-to-speech",
        "tools": ["text_to_speech"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "todo": {
        "description": "Task planning and tracking",
        "tools": ["todo"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "memory": {
        "description": "Persistent memory across sessions",
        "tools": ["memory"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "session_search": {
        "description": "Search and recall past conversations",
        "tools": ["session_search"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "clarify": {
        "description": "Ask the user clarifying questions",
        "tools": ["clarify"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "code_execution": {
        "description": "Run Python scripts that call tools programmatically",
        "tools": ["execute_code"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "delegation": {
        "description": "Spawn subagents for complex subtasks",
        "tools": ["delegate_task"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "honcho": {
        "description": "Honcho AI-native memory tools",
        "tools": ["honcho_context", "honcho_profile", "honcho_search", "honcho_conclude"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "homeassistant": {
        "description": "Home Assistant smart home control",
        "tools": ["ha_list_entities", "ha_get_state", "ha_list_services", "ha_call_service"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "debugging": {
        "description": "Debugging and troubleshooting toolkit",
        "tools": [],
        "includes": ["web", "file", "terminal"],
        "platforms": [],
        "legacy": False,
    },
    "safe": {
        "description": "Safe toolkit without terminal execution",
        "tools": ["memory", "session_search", "read_file", "search_files", "read", "find", "grep", "ls"],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "io-acp": {
        "description": "Editor integration toolset",
        "tools": [
            "web_search",
            "web_extract",
            "terminal",
            "process",
            "read_file",
            "write_file",
            "patch",
            "search_files",
            "vision_analyze",
            "skills_list",
            "skill_view",
            "skill_manage",
            "cronjob",
            "todo",
            "memory",
            "session_search",
            "execute_code",
            "delegate_task",
            "bash",
            "read",
            "write",
            "edit",
            "find",
            "grep",
            "ls",
        ],
        "includes": [],
        "platforms": [],
        "legacy": False,
    },
    "io-cli": {
        "description": "Full interactive CLI toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["cli"],
        "legacy": False,
    },
    "io-telegram": {
        "description": "Telegram bot toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["telegram"],
        "legacy": False,
    },
    "io-discord": {
        "description": "Discord bot toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["discord"],
        "legacy": False,
    },
    "io-whatsapp": {
        "description": "WhatsApp bot toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["whatsapp"],
        "legacy": False,
    },
    "io-slack": {
        "description": "Slack bot toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["slack"],
        "legacy": False,
    },
    "io-signal": {
        "description": "Signal bot toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["signal"],
        "legacy": False,
    },
    "io-homeassistant": {
        "description": "Home Assistant bot toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["homeassistant"],
        "legacy": False,
    },
    "io-email": {
        "description": "Email bot toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["email"],
        "legacy": False,
    },
    "io-sms": {
        "description": "SMS bot toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["sms"],
        "legacy": False,
    },
    "io-dingtalk": {
        "description": "DingTalk bot toolset",
        "tools": _IO_CORE_TOOLS,
        "includes": [],
        "platforms": ["dingtalk"],
        "legacy": False,
    },
    "io-gateway": {
        "description": "Union of all messaging platform toolsets",
        "tools": [],
        "includes": [
            "io-telegram",
            "io-discord",
            "io-whatsapp",
            "io-slack",
            "io-signal",
            "io-homeassistant",
            "io-email",
            "io-sms",
            "io-dingtalk",
        ],
        "platforms": [],
        "legacy": False,
    },
}

PLATFORM_DEFAULT_TOOLSETS: dict[str, list[str]] = {
    "cli": ["io-cli"],
    "telegram": ["io-telegram"],
    "discord": ["io-discord"],
    "slack": ["io-slack"],
    "whatsapp": ["io-whatsapp"],
    "signal": ["io-signal"],
    "email": ["io-email"],
    "sms": ["io-sms"],
    "homeassistant": ["io-homeassistant"],
    "dingtalk": ["io-dingtalk"],
}


@dataclass(frozen=True, slots=True)
class ToolsetSpec:
    name: str
    label: str
    description: str
    tools: tuple[str, ...]
    includes: tuple[str, ...] = ()
    platforms: tuple[str, ...] = ()
    legacy: bool = False


def _label_for(name: str) -> str:
    return name.replace("-", " ").title()


def get_toolset(name: str) -> dict[str, Any] | None:
    return _TOOLSETS.get(name)


def resolve_toolset(name: str, visited: set[str] | None = None) -> list[str]:
    if visited is None:
        visited = set()
    if name in {"all", "*"}:
        all_tools: set[str] = set()
        for toolset_name in get_toolset_names():
            all_tools.update(resolve_toolset(toolset_name, visited.copy()))
        return sorted(all_tools)
    if name in visited:
        return []
    visited.add(name)
    toolset = get_toolset(name)
    if not toolset:
        return []
    tools = set(toolset.get("tools", []))
    for included_name in toolset.get("includes", []):
        tools.update(resolve_toolset(included_name, visited.copy()))
    return sorted(tools)


def resolve_multiple_toolsets(toolset_names: list[str]) -> list[str]:
    all_tools: set[str] = set()
    for name in toolset_names:
        all_tools.update(resolve_toolset(name))
    return sorted(all_tools)


def get_all_toolsets() -> dict[str, dict[str, Any]]:
    return dict(_TOOLSETS)


def get_toolset_names() -> list[str]:
    return list(_TOOLSETS)


def validate_toolset(name: str) -> bool:
    return name in {"all", "*"} or name in _TOOLSETS


def create_custom_toolset(
    name: str,
    description: str,
    tools: list[str] | None = None,
    includes: list[str] | None = None,
) -> None:
    _TOOLSETS[name] = {
        "description": description,
        "tools": list(tools or []),
        "includes": list(includes or []),
        "platforms": [],
        "legacy": False,
    }


def get_toolset_info(name: str) -> dict[str, Any] | None:
    toolset = get_toolset(name)
    if not toolset:
        return None
    resolved_tools = resolve_toolset(name)
    return {
        "name": name,
        "description": toolset["description"],
        "direct_tools": list(toolset.get("tools", [])),
        "includes": list(toolset.get("includes", [])),
        "resolved_tools": resolved_tools,
        "tool_count": len(resolved_tools),
        "is_composite": bool(toolset.get("includes")),
        "platforms": list(toolset.get("platforms", [])),
        "legacy": bool(toolset.get("legacy", False)),
    }


def available_toolsets() -> list[ToolsetSpec]:
    specs: list[ToolsetSpec] = []
    for name, payload in sorted(_TOOLSETS.items()):
        if payload.get("legacy"):
            continue
        specs.append(
            ToolsetSpec(
                name=name,
                label=_label_for(name),
                description=str(payload.get("description", "")),
                tools=tuple(payload.get("tools", [])),
                includes=tuple(payload.get("includes", [])),
                platforms=tuple(payload.get("platforms", [])),
                legacy=bool(payload.get("legacy", False)),
            )
        )
    return specs


def default_toolsets_for_platform(platform: str = "cli") -> list[str]:
    return list(PLATFORM_DEFAULT_TOOLSETS.get(platform, ["io-cli"]))


def enabled_toolsets_for_platform(config: dict[str, Any], platform: str = "cli") -> list[str]:
    platform_toolsets = config.get("platform_toolsets", {})
    if isinstance(platform_toolsets, dict):
        configured = platform_toolsets.get(platform)
        if isinstance(configured, list) and configured:
            return [item for item in configured if validate_toolset(item)]
    if platform == "cli":
        configured = config.get("toolsets")
        if isinstance(configured, list) and configured:
            return [item for item in configured if validate_toolset(item)]
    return default_toolsets_for_platform(platform)


def set_toolset_enabled(
    config: dict[str, Any],
    toolset: str,
    enabled: bool,
    *,
    platform: str = "cli",
) -> dict[str, Any]:
    if not validate_toolset(toolset):
        raise KeyError(toolset)
    config.setdefault("platform_toolsets", {})
    current = enabled_toolsets_for_platform(config, platform)
    if enabled:
        if toolset not in current:
            current.append(toolset)
    else:
        current = [name for name in current if name != toolset]
    if not current:
        current = default_toolsets_for_platform(platform)
    config["platform_toolsets"][platform] = current
    if platform == "cli":
        config["toolsets"] = list(current)
    return config


def toolsets_status(config: dict[str, Any], platform: str = "cli") -> list[dict[str, Any]]:
    enabled = set(enabled_toolsets_for_platform(config, platform))
    rows: list[dict[str, Any]] = []
    for spec in available_toolsets():
        if spec.platforms and platform not in spec.platforms:
            continue
        resolved = resolve_toolset(spec.name)
        rows.append(
            {
                "name": spec.name,
                "label": spec.label,
                "description": spec.description,
                "tools": resolved,
                "enabled": spec.name in enabled,
                "platforms": list(spec.platforms),
            }
        )
    return rows


def enabled_tools_for_platform(
    config: dict[str, Any],
    *,
    platform: str = "cli",
    registry: ToolRegistry,
) -> list[dict[str, Any]]:
    enabled_toolsets = enabled_toolsets_for_platform(config, platform)
    tool_names = set(resolve_multiple_toolsets(enabled_toolsets))
    rows = []
    for tool_name in sorted(registry.names()):
        if tool_name not in tool_names:
            continue
        tool = registry.get(tool_name)
        rows.append({"name": tool.name, "description": tool.description, "enabled": True})
    return rows


def build_toolset_resolver() -> ToolsetResolver:
    resolved = {name: set(resolve_toolset(name)) for name in _TOOLSETS}
    return ToolsetResolver(toolsets=resolved)
