"""SkillTool - Dynamic skill discovery and execution.

Discovers and executes skills from the skills directory dynamically.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from io_agent import Tool, ToolContext, ToolResult


class SkillTool(Tool):
    """Dynamically discover and execute skills."""

    name = "skill"
    description = "Discover and execute skills dynamically. Skills are loaded from the skills directory and can be invoked by name."

    async def execute(
        self,
        skill_name: str,
        action: str = "execute",
        parameters: dict[str, Any] | None = None,
        context: ToolContext | None = None,
    ) -> ToolResult:
        """Execute a skill.

        Args:
            skill_name: Name of the skill to execute
            action: Action to perform (list, describe, execute)
            parameters: Parameters to pass to the skill
            context: Tool execution context
        """
        home = Path.home() / ".io"
        skills_dir = home.parent / "skills" if (home.parent / "skills").exists() else Path("skills")

        if action == "list":
            return await self._list_skills(skills_dir)
        elif action == "describe":
            return await self._describe_skill(skills_dir, skill_name)
        elif action == "execute":
            return await self._execute_skill(skills_dir, skill_name, parameters or {})
        else:
            return ToolResult(content=f"❌ Unknown action: {action}", is_error=True)

    async def _list_skills(self, skills_dir: Path) -> ToolResult:
        """List available skills."""
        if not skills_dir.exists():
            return ToolResult(content="📂 No skills directory found")

        skills = []
        for skill_file in skills_dir.glob("*.json"):
            try:
                data = json.loads(skill_file.read_text())
                skills.append(
                    {
                        "name": data.get("name", skill_file.stem),
                        "description": data.get("description", "No description"),
                        "version": data.get("version", "0.1.0"),
                    }
                )
            except (json.JSONDecodeError, KeyError):
                continue

        if not skills:
            return ToolResult(content="📂 No skills found")

        lines = [f"🛠️ Available Skills ({len(skills)}):"]
        for skill in sorted(skills, key=lambda x: x["name"]):
            lines.append(f"  • {skill['name']} v{skill['version']}")
            lines.append(f"    {skill['description']}")

        return ToolResult(content="\n".join(lines), data={"skills": skills})

    async def _describe_skill(self, skills_dir: Path, skill_name: str) -> ToolResult:
        """Describe a specific skill."""
        skill_file = skills_dir / f"{skill_name}.json"

        if not skill_file.exists():
            return ToolResult(content=f"❌ Skill not found: {skill_name}", is_error=True)

        try:
            data = json.loads(skill_file.read_text())
            lines = [
                f"🛠️ Skill: {data.get('name', skill_name)}",
                f"Version: {data.get('version', '0.1.0')}",
                f"Description: {data.get('description', 'No description')}",
            ]

            if "parameters" in data:
                lines.append("\nParameters:")
                for param, info in data["parameters"].items():
                    required = "required" if info.get("required") else "optional"
                    lines.append(f"  • {param} ({required}): {info.get('description', '')}")

            return ToolResult(content="\n".join(lines), data=data)
        except json.JSONDecodeError:
            return ToolResult(content=f"❌ Invalid skill file: {skill_name}", is_error=True)

    async def _execute_skill(
        self, skills_dir: Path, skill_name: str, parameters: dict
    ) -> ToolResult:
        """Execute a skill."""
        skill_file = skills_dir / f"{skill_name}.json"

        if not skill_file.exists():
            return ToolResult(content=f"❌ Skill not found: {skill_name}", is_error=True)

        try:
            data = json.loads(skill_file.read_text())

            # Execute skill logic
            skill_type = data.get("type", "command")

            if skill_type == "command":
                # Execute shell command
                import subprocess

                command = data.get("command", "").format(**parameters)
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                return ToolResult(
                    content=result.stdout if result.returncode == 0 else result.stderr,
                    is_error=result.returncode != 0,
                    data={"returncode": result.returncode},
                )

            elif skill_type == "prompt":
                # Return prompt template
                prompt = data.get("prompt", "").format(**parameters)
                return ToolResult(
                    content=f"📝 Skill prompt generated:\n{prompt}",
                    data={"prompt": prompt},
                )

            else:
                return ToolResult(content=f"⚠️ Unknown skill type: {skill_type}")

        except Exception as e:
            return ToolResult(content=f"❌ Error executing skill: {e}", is_error=True)
