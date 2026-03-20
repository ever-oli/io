"""IO-compatible cronjob management tool."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..cron import CronManager


_CRON_THREAT_PATTERNS = [
    (r"ignore\s+(?:\w+\s+)*(?:previous|all|above|prior)\s+(?:\w+\s+)*instructions", "prompt_injection"),
    (r"do\s+not\s+tell\s+the\s+user", "deception_hide"),
    (r"system\s+prompt\s+override", "sys_prompt_override"),
    (r"disregard\s+(your|all|any)\s+(instructions|rules|guidelines)", "disregard_rules"),
    (r"curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_curl"),
    (r"wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_wget"),
    (r"cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass)", "read_secrets"),
    (r"authorized_keys", "ssh_backdoor"),
    (r"/etc/sudoers|visudo", "sudoers_mod"),
    (r"rm\s+-rf\s+/", "destructive_root_rm"),
]

_CRON_INVISIBLE_CHARS = {
    "\u200b",
    "\u200c",
    "\u200d",
    "\u2060",
    "\ufeff",
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
}


def _scan_cron_prompt(prompt: str) -> str:
    for char in _CRON_INVISIBLE_CHARS:
        if char in prompt:
            return f"Blocked: prompt contains invisible unicode U+{ord(char):04X}."
    for pattern, label in _CRON_THREAT_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return f"Blocked: prompt matches threat pattern '{label}'."
    return ""


def _canonical_skills(skill: str | None = None, skills: Any | None = None) -> list[str]:
    if skills is None:
        raw_items = [skill] if skill else []
    elif isinstance(skills, str):
        raw_items = [skills]
    else:
        raw_items = list(skills)
    normalized: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_optional_value(value: Any, *, strip_trailing_slash: bool = False) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if strip_trailing_slash:
        text = text.rstrip("/")
    return text or None


def _origin_from_env(env: dict[str, str]) -> dict[str, str] | None:
    platform = env.get("IO_SESSION_PLATFORM") or env.get("IO_SESSION_PLATFORM")
    chat_id = env.get("IO_SESSION_CHAT_ID") or env.get("IO_SESSION_CHAT_ID")
    if platform and chat_id:
        return {
            "platform": platform,
            "chat_id": chat_id,
            "chat_name": env.get("IO_SESSION_CHAT_NAME") or env.get("IO_SESSION_CHAT_NAME"),
            "thread_id": env.get("IO_SESSION_THREAD_ID") or env.get("IO_SESSION_THREAD_ID"),
        }
    return None


def _repeat_display(job: dict[str, Any]) -> str:
    repeat = job.get("repeat") or {}
    times = repeat.get("times")
    completed = int(repeat.get("completed", 0) or 0)
    if times is None:
        return "forever"
    if times == 1:
        return "once" if completed == 0 else "1/1"
    return f"{completed}/{times}" if completed else f"{times} times"


def _format_job(job: dict[str, Any]) -> dict[str, Any]:
    prompt = str(job.get("prompt", ""))
    skills = _canonical_skills(skills=job.get("skills"))
    return {
        "job_id": job["id"],
        "name": job["name"],
        "skill": skills[0] if skills else None,
        "skills": skills,
        "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
        "model": job.get("model"),
        "provider": job.get("provider"),
        "base_url": job.get("base_url"),
        "schedule": job.get("schedule_display") or job.get("schedule"),
        "repeat": _repeat_display(job),
        "deliver": job.get("deliver", "local"),
        "next_run_at": job.get("next_run_at"),
        "last_run_at": job.get("last_run_at"),
        "last_status": job.get("last_status"),
        "enabled": job.get("enabled", True),
        "state": job.get("state", "scheduled" if job.get("enabled", True) else "paused"),
        "paused_at": job.get("paused_at"),
        "paused_reason": job.get("paused_reason"),
    }


def check_cronjob_requirements() -> bool:
    env = os.environ
    return bool(
        env.get("IO_INTERACTIVE")
        or env.get("IO_GATEWAY_SESSION")
        or env.get("IO_EXEC_ASK")
        or env.get("IO_INTERACTIVE")
        or env.get("IO_GATEWAY_SESSION")
        or env.get("IO_EXEC_ASK")
    )


def cronjob(
    action: str,
    job_id: str | None = None,
    prompt: str | None = None,
    schedule: str | None = None,
    name: str | None = None,
    repeat: int | None = None,
    deliver: str | None = None,
    include_disabled: bool = False,
    skill: str | None = None,
    skills: list[str] | None = None,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    reason: str | None = None,
    task_id: str | None = None,
    *,
    home=None,
    cwd=None,
    env: dict[str, str] | None = None,
) -> str:
    del task_id
    manager = CronManager(home=home)
    resolved_env = env or {}
    normalized = (action or "").strip().lower()
    try:
        if normalized == "create":
            if not schedule:
                return json.dumps({"success": False, "error": "schedule is required for create"}, indent=2)
            canonical_skills = _canonical_skills(skill, skills)
            if not prompt and not canonical_skills:
                return json.dumps(
                    {
                        "success": False,
                        "error": "create requires either prompt or at least one skill",
                    },
                    indent=2,
                )
            if prompt:
                scan_error = _scan_cron_prompt(prompt)
                if scan_error:
                    return json.dumps({"success": False, "error": scan_error}, indent=2)
            job = manager.create_job(
                prompt=prompt or "",
                schedule=schedule,
                cwd=cwd,
                name=name,
                repeat=repeat,
                deliver=deliver,
                skills=canonical_skills,
                model=_normalize_optional_value(model),
                provider=_normalize_optional_value(provider),
                base_url=_normalize_optional_value(base_url, strip_trailing_slash=True),
                origin=_origin_from_env(resolved_env),
            )
            return json.dumps(
                {
                    "success": True,
                    "job_id": job["id"],
                    "name": job["name"],
                    "skill": canonical_skills[0] if canonical_skills else None,
                    "skills": canonical_skills,
                    "schedule": job["schedule_display"],
                    "repeat": _repeat_display(job),
                    "deliver": job.get("deliver", "local"),
                    "next_run_at": job.get("next_run_at"),
                    "job": _format_job(job),
                    "message": f"Cron job '{job['name']}' created.",
                },
                indent=2,
            )

        if normalized == "list":
            jobs = [_format_job(job) for job in manager.list_jobs(include_disabled=include_disabled)]
            return json.dumps({"success": True, "count": len(jobs), "jobs": jobs}, indent=2)

        if not job_id:
            return json.dumps(
                {"success": False, "error": f"job_id is required for action '{normalized}'"},
                indent=2,
            )

        job = manager.get_job(job_id)
        if job is None:
            return json.dumps(
                {
                    "success": False,
                    "error": f"Job with ID '{job_id}' not found. Use cronjob(action='list') to inspect jobs.",
                },
                indent=2,
            )

        if normalized == "remove":
            removed = manager.remove_job(job_id)
            return json.dumps(
                {
                    "success": True,
                    "message": f"Cron job '{removed['name']}' removed.",
                    "removed_job": {
                        "id": removed["id"],
                        "name": removed["name"],
                        "schedule": removed.get("schedule_display") or removed.get("schedule"),
                    },
                },
                indent=2,
            )

        if normalized == "pause":
            updated = manager.pause_job(job_id, reason=reason)
            return json.dumps({"success": True, "job": _format_job(updated)}, indent=2)

        if normalized == "resume":
            updated = manager.resume_job(job_id)
            return json.dumps({"success": True, "job": _format_job(updated)}, indent=2)

        if normalized in {"run", "run_now", "trigger"}:
            updated = manager.run_job_sync(
                job_id,
                model=_normalize_optional_value(model),
                provider=_normalize_optional_value(provider),
                base_url=_normalize_optional_value(base_url, strip_trailing_slash=True),
            )
            payload: dict[str, Any] = {"success": "error" not in updated, "job": _format_job(updated)}
            if "result" in updated:
                payload["result"] = updated["result"]
            if "session_path" in updated:
                payload["session_path"] = updated["session_path"]
            if "error" in updated:
                payload["error"] = updated["error"]
            return json.dumps(payload, indent=2)

        if normalized == "update":
            updates: dict[str, Any] = {}
            if prompt is not None:
                scan_error = _scan_cron_prompt(prompt)
                if scan_error:
                    return json.dumps({"success": False, "error": scan_error}, indent=2)
                updates["prompt"] = prompt
            if name is not None:
                updates["name"] = name
            if deliver is not None:
                updates["deliver"] = deliver
            if skills is not None or skill is not None:
                updates["skills"] = _canonical_skills(skill, skills)
            if schedule is not None:
                updates["schedule"] = schedule
            if repeat is not None:
                updates["repeat"] = repeat
            if model is not None:
                updates["model"] = _normalize_optional_value(model)
            if provider is not None:
                updates["provider"] = _normalize_optional_value(provider)
            if base_url is not None:
                updates["base_url"] = _normalize_optional_value(base_url, strip_trailing_slash=True)
            if not updates:
                return json.dumps({"success": False, "error": "No updates provided."}, indent=2)
            updated = manager.update_job(job_id, **updates)
            return json.dumps({"success": True, "job": _format_job(updated)}, indent=2)

        return json.dumps({"success": False, "error": f"Unknown cron action '{action}'"}, indent=2)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


def schedule_cronjob(
    prompt: str,
    schedule: str,
    name: str | None = None,
    repeat: int | None = None,
    deliver: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    task_id: str | None = None,
    *,
    home=None,
    cwd=None,
    env: dict[str, str] | None = None,
) -> str:
    return cronjob(
        action="create",
        prompt=prompt,
        schedule=schedule,
        name=name,
        repeat=repeat,
        deliver=deliver,
        model=model,
        provider=provider,
        base_url=base_url,
        task_id=task_id,
        home=home,
        cwd=cwd,
        env=env,
    )


def list_cronjobs(include_disabled: bool = False, task_id: str | None = None, *, home=None) -> str:
    return cronjob(action="list", include_disabled=include_disabled, task_id=task_id, home=home)


def remove_cronjob(job_id: str, task_id: str | None = None, *, home=None) -> str:
    return cronjob(action="remove", job_id=job_id, task_id=task_id, home=home)


CRONJOB_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "One of: create, list, update, pause, resume, remove, run",
        },
        "job_id": {
            "type": "string",
            "description": "Required for update/pause/resume/remove/run",
        },
        "prompt": {
            "type": "string",
            "description": "The self-contained prompt for the scheduled job.",
        },
        "schedule": {
            "type": "string",
            "description": "Schedule string such as '30m', 'every 2h', '0 9 * * *', or 'manual'.",
        },
        "name": {
            "type": "string",
            "description": "Optional human-friendly name",
        },
        "repeat": {
            "type": "integer",
            "description": "Optional repeat count. Omit for recurring/manual defaults.",
        },
        "deliver": {
            "type": "string",
            "description": "Delivery target: origin, local, telegram, discord, signal, sms, or platform:chat_id",
        },
        "model": {
            "type": "string",
            "description": "Optional per-job model override",
        },
        "provider": {
            "type": "string",
            "description": "Optional per-job provider override",
        },
        "base_url": {
            "type": "string",
            "description": "Optional per-job base URL override",
        },
        "include_disabled": {
            "type": "boolean",
            "description": "For list: include paused/completed jobs",
        },
        "skill": {
            "type": "string",
            "description": "Optional single skill name to attach to the job",
        },
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional ordered list of skills to attach to the job",
        },
        "reason": {
            "type": "string",
            "description": "Optional pause reason",
        },
    },
    "required": ["action"],
}


def get_cronjob_tool_definitions() -> list[dict[str, Any]]:
    return [{"name": "cronjob", "description": "Manage scheduled cron jobs.", "parameters": CRONJOB_SCHEMA}]


class CronjobTool(Tool):
    name = "cronjob"
    description = (
        "Manage scheduled cron jobs with a single compressed tool. "
        "Use action=create/list/update/pause/resume/remove/run."
    )
    input_schema = CRONJOB_SCHEMA
    never_parallel = True

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        action = str(arguments.get("action", ""))
        normalized = action.strip().lower()
        if normalized in {"run", "run_now", "trigger"}:
            manager = CronManager(home=context.home)
            job_id = _normalize_optional_value(arguments.get("job_id"))
            if not job_id:
                payload = json.dumps(
                    {"success": False, "error": "job_id is required for action 'run'"},
                    indent=2,
                )
                return ToolResult(content=payload, is_error=True)
            updated = await manager.run_job(
                job_id,
                model=_normalize_optional_value(arguments.get("model")),
                provider=_normalize_optional_value(arguments.get("provider")),
                base_url=_normalize_optional_value(
                    arguments.get("base_url"),
                    strip_trailing_slash=True,
                ),
            )
            payload_data: dict[str, Any] = {
                "success": "error" not in updated,
                "job": _format_job(updated),
            }
            if "result" in updated:
                payload_data["result"] = updated["result"]
            if "session_path" in updated:
                payload_data["session_path"] = updated["session_path"]
            if "error" in updated:
                payload_data["error"] = updated["error"]
            payload = json.dumps(payload_data, indent=2)
            return ToolResult(content=payload, is_error=not bool(payload_data["success"]))

        payload = cronjob(
            action=action,
            job_id=_normalize_optional_value(arguments.get("job_id")),
            prompt=_normalize_optional_value(arguments.get("prompt")),
            schedule=_normalize_optional_value(arguments.get("schedule")),
            name=_normalize_optional_value(arguments.get("name")),
            repeat=int(arguments["repeat"]) if arguments.get("repeat") is not None else None,
            deliver=_normalize_optional_value(arguments.get("deliver")),
            include_disabled=bool(arguments.get("include_disabled", False)),
            skill=_normalize_optional_value(arguments.get("skill")),
            skills=list(arguments.get("skills", [])) if isinstance(arguments.get("skills"), list) else None,
            model=_normalize_optional_value(arguments.get("model")),
            provider=_normalize_optional_value(arguments.get("provider")),
            base_url=_normalize_optional_value(arguments.get("base_url"), strip_trailing_slash=True),
            reason=_normalize_optional_value(arguments.get("reason")),
            home=context.home,
            cwd=context.cwd,
            env={**os.environ, **context.env},
        )
        result = json.loads(payload)
        return ToolResult(content=payload, is_error=not bool(result.get("success")))


GLOBAL_TOOL_REGISTRY.register(CronjobTool())
