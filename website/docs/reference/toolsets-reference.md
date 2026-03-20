---
sidebar_position: 4
title: "Toolsets Reference"
description: "Reference for IO core, composite, platform, and dynamic toolsets"
---

# Toolsets Reference

Toolsets are named bundles of tools that you can enable with `io chat --toolsets ...`, configure per platform, or resolve inside the agent runtime.

| Toolset | Kind | Resolves to |
|---------|------|-------------|
| `browser` | core | `browser_back`, `browser_click`, `browser_close`, `browser_console`, `browser_get_images`, `browser_navigate`, `browser_press`, `browser_scroll`, `browser_snapshot`, `browser_type`, `browser_vision`, `web_search` |
| `clarify` | core | `clarify` |
| `code_execution` | core | `execute_code` |
| `cronjob` | core | `cronjob` |
| `debugging` | composite | `patch`, `process`, `read_file`, `search_files`, `terminal`, `web_extract`, `web_search`, `write_file` |
| `delegation` | core | `delegate_task` |
| `file` | core | `patch`, `read_file`, `search_files`, `write_file` |
| `io-acp` | platform | `browser_back`, `browser_click`, `browser_close`, `browser_console`, `browser_get_images`, `browser_navigate`, `browser_press`, `browser_scroll`, `browser_snapshot`, `browser_type`, `browser_vision`, `delegate_task`, `execute_code`, `memory`, `patch`, `process`, `read_file`, `search_files`, `session_search`, `skill_manage`, `skill_view`, `skills_list`, `terminal`, `todo`, `vision_analyze`, `web_extract`, `web_search`, `write_file` |
| `io-cli` | platform | `browser_back`, `browser_click`, `browser_close`, `browser_console`, `browser_get_images`, `browser_navigate`, `browser_press`, `browser_scroll`, `browser_snapshot`, `browser_type`, `browser_vision`, `clarify`, `cronjob`, `delegate_task`, `execute_code`, `ha_call_service`, `ha_get_state`, `ha_list_entities`, `ha_list_services`, `honcho_conclude`, `honcho_context`, `honcho_profile`, `honcho_search`, `image_generate`, `memory`, `mixture_of_agents`, `patch`, `process`, `read_file`, `search_files`, `send_message`, `session_search`, `skill_manage`, `skill_view`, `skills_list`, `terminal`, `text_to_speech`, `todo`, `vision_analyze`, `web_extract`, `web_search`, `write_file` |
| `io-discord` | platform | _(same as io-cli)_ |
| `io-email` | platform | _(same as io-cli)_ |
| `io-gateway` | composite | Union of all messaging platform toolsets |
| `io-homeassistant` | platform | _(same as io-cli)_ |
| `io-signal` | platform | _(same as io-cli)_ |
| `io-slack` | platform | _(same as io-cli)_ |
| `io-sms` | platform | _(same as io-cli)_ |
| `io-telegram` | platform | _(same as io-cli)_ |
| `io-whatsapp` | platform | _(same as io-cli)_ |
| `homeassistant` | core | `ha_call_service`, `ha_get_state`, `ha_list_entities`, `ha_list_services` |
| `honcho` | core | `honcho_conclude`, `honcho_context`, `honcho_profile`, `honcho_search` |
| `image_gen` | core | `image_generate` |
| `memory` | core | `memory` |
| `messaging` | core | `send_message` |
| `moa` | core | `mixture_of_agents` |
| `rl` | core | `rl_check_status`, `rl_edit_config`, `rl_get_current_config`, `rl_get_results`, `rl_list_environments`, `rl_list_runs`, `rl_select_environment`, `rl_start_training`, `rl_stop_training`, `rl_test_inference` |
| `safe` | composite | `image_generate`, `mixture_of_agents`, `vision_analyze`, `web_extract`, `web_search` |
| `search` | core | `web_search` |
| `session_search` | core | `session_search` |
| `skills` | core | `skill_manage`, `skill_view`, `skills_list` |
| `terminal` | core | `process`, `terminal` |
| `todo` | core | `todo` |
| `tts` | core | `text_to_speech` |
| `vision` | core | `vision_analyze` |
| `web` | core | `web_extract`, `web_search` |

## Dynamic toolsets

- `mcp-<server>` Φ generated at runtime for each configured MCP server.
- Custom toolsets can be created in configuration and resolved at startup.
- Wildcards: `all` and `*` expand to every registered toolset.