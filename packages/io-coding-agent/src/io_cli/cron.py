"""IO-style cron job storage and execution for IO."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import ensure_io_home
from .gateway import GatewayManager

try:
    from croniter import croniter

    HAS_CRONITER = True
except Exception:
    HAS_CRONITER = False


ONESHOT_GRACE_SECONDS = 120


def _now_dt() -> datetime:
    return datetime.now().astimezone()


def _now() -> str:
    return _now_dt().isoformat()


def _normalize_deliver(value: str | list[str] | None) -> str:
    if value is None:
        return "local"
    if isinstance(value, list):
        for item in value:
            text = str(item).strip()
            if text:
                return text
        return "local"
    text = str(value).strip()
    return text or "local"


def _normalize_skills(value: list[str] | None) -> list[str]:
    if not value:
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_repeat(value: int | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, dict):
        times = value.get("times")
        completed = value.get("completed", 0)
        return {
            "times": int(times) if times is not None else None,
            "completed": max(0, int(completed or 0)),
        }
    if value is None:
        return {"times": None, "completed": 0}
    return {"times": max(0, int(value)), "completed": 0}


def parse_duration(value: str) -> int:
    text = value.strip().lower()
    match = re.match(r"^(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$", text)
    if not match:
        raise ValueError(f"Invalid duration: {value!r}")
    amount = int(match.group(1))
    unit = match.group(2)[0]
    multipliers = {"m": 1, "h": 60, "d": 1440}
    return amount * multipliers[unit]


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_now_dt().tzinfo)
    return value.astimezone(_now_dt().tzinfo)


def parse_schedule(schedule: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(schedule, dict):
        return dict(schedule)

    original = str(schedule or "").strip()
    if not original:
        raise ValueError("Schedule cannot be empty.")
    lowered = original.lower()

    if lowered == "manual":
        return {"kind": "manual", "display": "manual"}

    if lowered.startswith("every "):
        minutes = parse_duration(original[6:].strip())
        return {"kind": "interval", "minutes": minutes, "display": f"every {minutes}m"}

    parts = original.split()
    if len(parts) >= 5 and all(re.match(r"^[\d\*\-,/]+$", part) for part in parts[:5]):
        if not HAS_CRONITER:
            raise ValueError("Cron expressions require the optional 'croniter' package.")
        try:
            croniter(original)
        except Exception as exc:
            raise ValueError(f"Invalid cron expression {original!r}: {exc}") from exc
        return {"kind": "cron", "expr": original, "display": original}

    if "T" in original or re.match(r"^\d{4}-\d{2}-\d{2}", original):
        try:
            run_at = datetime.fromisoformat(original.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"Invalid timestamp {original!r}: {exc}") from exc
        run_at = _ensure_aware(run_at)
        return {
            "kind": "once",
            "run_at": run_at.isoformat(),
            "display": f"once at {run_at.strftime('%Y-%m-%d %H:%M')}",
        }

    try:
        minutes = parse_duration(original)
    except ValueError as exc:
        raise ValueError(
            "Invalid schedule. Use 'manual', '30m', 'every 2h', '0 9 * * *', "
            "or an ISO timestamp like '2026-02-03T14:00:00'."
        ) from exc
    run_at = _now_dt() + timedelta(minutes=minutes)
    return {"kind": "once", "run_at": run_at.isoformat(), "display": f"once in {original}"}


def _recoverable_oneshot_run_at(
    schedule: dict[str, Any],
    now: datetime,
    *,
    last_run_at: str | None = None,
) -> str | None:
    if schedule.get("kind") != "once" or last_run_at:
        return None
    run_at = schedule.get("run_at")
    if not run_at:
        return None
    run_at_dt = _ensure_aware(datetime.fromisoformat(str(run_at)))
    if run_at_dt >= now - timedelta(seconds=ONESHOT_GRACE_SECONDS):
        return run_at_dt.isoformat()
    return None


def compute_next_run(schedule: dict[str, Any], last_run_at: str | None = None) -> str | None:
    now = _now_dt()
    kind = schedule.get("kind")
    if kind == "manual":
        return None
    if kind == "once":
        return _recoverable_oneshot_run_at(schedule, now, last_run_at=last_run_at)
    if kind == "interval":
        minutes = int(schedule.get("minutes", 0) or 0)
        if minutes <= 0:
            return None
        if last_run_at:
            next_run = _ensure_aware(datetime.fromisoformat(last_run_at)) + timedelta(minutes=minutes)
        else:
            next_run = now + timedelta(minutes=minutes)
        return next_run.isoformat()
    if kind == "cron":
        if not HAS_CRONITER:
            return None
        next_run = croniter(str(schedule.get("expr", "")), now).get_next(datetime)
        return _ensure_aware(next_run).isoformat()
    return None


@dataclass(slots=True)
class CronJob:
    id: str
    name: str
    prompt: str
    schedule: dict[str, Any] | str
    cwd: str
    schedule_display: str = ""
    deliver: str | list[str] = "local"
    skills: list[str] = field(default_factory=list)
    repeat: dict[str, Any] = field(default_factory=lambda: {"times": None, "completed": 0})
    model: str | None = None
    provider: str | None = None
    base_url: str | None = None
    next_run_at: str | None = None
    enabled: bool = True
    state: str = "scheduled"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    last_run_at: str | None = None
    last_status: str | None = None
    last_result: str | None = None
    last_error: str | None = None
    last_session_path: str | None = None
    last_output_path: str | None = None
    paused_at: str | None = None
    paused_reason: str | None = None
    origin: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self.schedule = parse_schedule(self.schedule)
        self.schedule_display = self.schedule_display or str(self.schedule.get("display", "manual"))
        self.deliver = _normalize_deliver(self.deliver)
        self.skills = _normalize_skills(self.skills)
        self.repeat = _normalize_repeat(self.repeat)
        if self.base_url:
            self.base_url = self.base_url.rstrip("/") or None
        if self.enabled and self.state != "paused" and not self.next_run_at:
            self.next_run_at = compute_next_run(self.schedule, self.last_run_at)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CronManager:
    def __init__(self, home: Path | None = None) -> None:
        self.home = ensure_io_home(home)
        self.cron_dir = self.home / "cron"
        self.output_dir = self.cron_dir / "output"
        self.cron_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_path = self.cron_dir / "jobs.json"

    def _load_jobs(self) -> list[CronJob]:
        if not self.jobs_path.exists():
            return []
        payload = json.loads(self.jobs_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("jobs", [])
        if not isinstance(payload, list):
            return []
        return [CronJob(**item) for item in payload if isinstance(item, dict)]

    def _save_jobs(self, jobs: list[CronJob]) -> None:
        fd, tmp_path = tempfile.mkstemp(dir=str(self.cron_dir), suffix=".tmp", prefix=".jobs_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {"jobs": [job.to_dict() for job in jobs], "updated_at": _now()},
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.jobs_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _save_output(self, job_id: str, output: str) -> Path:
        job_output_dir = self.output_dir / job_id
        job_output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = _now_dt().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = job_output_dir / f"{timestamp}.md"
        fd, tmp_path = tempfile.mkstemp(dir=str(job_output_dir), suffix=".tmp", prefix=".output_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(output)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, output_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return output_path

    def list_jobs(self, *, include_disabled: bool = True) -> list[dict[str, Any]]:
        jobs = self._load_jobs()
        if not include_disabled:
            jobs = [job for job in jobs if job.enabled]
        return [job.to_dict() for job in jobs]

    def get_job(self, job_id: str) -> CronJob | None:
        for job in self._load_jobs():
            if job.id == job_id:
                return job
        return None

    def create_job(
        self,
        *,
        prompt: str,
        schedule: str,
        cwd: Path,
        name: str | None = None,
        deliver: str | list[str] | None = None,
        skills: list[str] | None = None,
        repeat: int | dict[str, Any] | None = None,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        origin: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        jobs = self._load_jobs()
        parsed_schedule = parse_schedule(schedule)
        normalized_repeat = _normalize_repeat(repeat)
        if parsed_schedule.get("kind") == "once" and repeat is None:
            normalized_repeat = {"times": 1, "completed": 0}
        job = CronJob(
            id=uuid.uuid4().hex[:12],
            name=name or (prompt[:50].strip() or "cron job"),
            prompt=prompt,
            schedule=parsed_schedule,
            cwd=str(cwd.resolve()),
            schedule_display=str(parsed_schedule.get("display", schedule)),
            deliver=_normalize_deliver(deliver),
            skills=_normalize_skills(skills),
            repeat=normalized_repeat,
            model=model.strip() if isinstance(model, str) and model.strip() else None,
            provider=provider.strip() if isinstance(provider, str) and provider.strip() else None,
            base_url=base_url.rstrip("/") if isinstance(base_url, str) else base_url,
            next_run_at=compute_next_run(parsed_schedule),
            origin=origin,
        )
        jobs.append(job)
        self._save_jobs(jobs)
        return job.to_dict()

    def update_job(self, job_id: str, **changes: Any) -> dict[str, Any]:
        jobs = self._load_jobs()
        for index, job in enumerate(jobs):
            if job.id != job_id:
                continue
            if "schedule" in changes and changes["schedule"] is not None:
                parsed_schedule = parse_schedule(changes["schedule"])
                job.schedule = parsed_schedule
                job.schedule_display = str(parsed_schedule.get("display", changes["schedule"]))
                if job.state != "paused":
                    job.next_run_at = compute_next_run(parsed_schedule, job.last_run_at)
            for key, value in changes.items():
                if key == "schedule" or value is None or not hasattr(job, key):
                    continue
                if key == "deliver":
                    value = _normalize_deliver(value)
                elif key == "skills":
                    value = _normalize_skills(value)
                elif key == "repeat":
                    value = _normalize_repeat(value)
                elif key == "base_url" and isinstance(value, str):
                    value = value.rstrip("/") or None
                setattr(job, key, value)
            if job.enabled and job.state != "paused" and not job.next_run_at:
                job.next_run_at = compute_next_run(job.schedule, job.last_run_at)
            job.updated_at = _now()
            jobs[index] = job
            self._save_jobs(jobs)
            return job.to_dict()
        raise KeyError(job_id)

    def pause_job(self, job_id: str, reason: str | None = None) -> dict[str, Any]:
        return self.update_job(
            job_id,
            enabled=False,
            state="paused",
            paused_at=_now(),
            paused_reason=reason,
        )

    def resume_job(self, job_id: str) -> dict[str, Any]:
        return self.update_job(
            job_id,
            enabled=True,
            state="scheduled",
            paused_at=None,
            paused_reason=None,
            next_run_at=None,
        )

    def trigger_job(self, job_id: str) -> dict[str, Any]:
        return self.update_job(
            job_id,
            enabled=True,
            state="scheduled",
            paused_at=None,
            paused_reason=None,
            next_run_at=_now(),
        )

    def remove_job(self, job_id: str) -> dict[str, Any]:
        jobs = self._load_jobs()
        remaining = [job for job in jobs if job.id != job_id]
        if len(remaining) == len(jobs):
            raise KeyError(job_id)
        removed = next(job for job in jobs if job.id == job_id)
        self._save_jobs(remaining)
        return removed.to_dict()

    def get_due_jobs(self) -> list[CronJob]:
        now = _now_dt()
        raw_jobs = self._load_jobs()
        jobs = copy.deepcopy(raw_jobs)
        due: list[CronJob] = []
        needs_save = False

        for job in jobs:
            if not job.enabled:
                continue

            next_run = job.next_run_at
            if not next_run:
                recovered = _recoverable_oneshot_run_at(job.schedule, now, last_run_at=job.last_run_at)
                if not recovered:
                    continue
                job.next_run_at = recovered
                next_run = recovered
                for stored_job in raw_jobs:
                    if stored_job.id == job.id:
                        stored_job.next_run_at = recovered
                        needs_save = True
                        break

            next_run_dt = _ensure_aware(datetime.fromisoformat(next_run))
            if next_run_dt > now:
                continue

            kind = str(job.schedule.get("kind", ""))
            if kind in {"interval", "cron"} and (now - next_run_dt).total_seconds() > 120:
                new_next = compute_next_run(job.schedule, now.isoformat())
                if new_next:
                    for stored_job in raw_jobs:
                        if stored_job.id == job.id:
                            stored_job.next_run_at = new_next
                            needs_save = True
                            break
                    continue

            due.append(job)

        if needs_save:
            self._save_jobs(raw_jobs)
        return due

    async def run_job(
        self,
        job_id: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if not job.enabled and job.state == "paused":
            raise ValueError(f"Job {job_id} is paused.")

        from .main import run_prompt

        try:
            result = await run_prompt(
                job.prompt,
                cwd=Path(job.cwd),
                home=self.home,
                model=model or job.model,
                provider=provider or job.provider,
                base_url=base_url or job.base_url,
            )
        except Exception as exc:
            next_run_at = compute_next_run(job.schedule, _now())
            updated = self.update_job(
                job_id,
                state="scheduled" if next_run_at else "failed",
                enabled=bool(next_run_at) if job.schedule.get("kind") != "manual" else False,
                next_run_at=next_run_at,
                last_run_at=_now(),
                last_status="failed",
                last_error=str(exc),
                last_result=str(exc),
            )
            updated["error"] = str(exc)
            return updated

        output_path = self._save_output(job_id, result.text)
        repeat = _normalize_repeat(job.repeat)
        repeat["completed"] = int(repeat.get("completed", 0) or 0) + 1
        times = repeat.get("times")
        exhausted = times is not None and repeat["completed"] >= times
        last_run_at = _now()
        next_run_at = None if exhausted else compute_next_run(job.schedule, last_run_at)
        enabled = job.enabled and not exhausted and next_run_at is not None
        state = "completed" if not enabled else "scheduled"
        updated = self.update_job(
            job_id,
            state=state,
            enabled=enabled,
            repeat=repeat,
            next_run_at=next_run_at,
            last_run_at=last_run_at,
            last_status="completed",
            last_error=None,
            last_result=result.text,
            last_session_path=str(result.session_path),
            last_output_path=str(output_path),
        )
        updated["result"] = result.text
        updated["session_path"] = str(result.session_path)
        updated["output_path"] = str(output_path)
        return updated

    def run_job_sync(
        self,
        job_id: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        return asyncio.run(self.run_job(job_id, model=model, provider=provider, base_url=base_url))

    def tick_sync(
        self,
        *,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            self.run_job_sync(job.id, model=model, provider=provider, base_url=base_url)
            for job in self.get_due_jobs()
        ]

    def status(self) -> dict[str, Any]:
        jobs = self._load_jobs()
        gateway = GatewayManager(home=self.home).status()
        next_runs = [job.next_run_at for job in jobs if job.enabled and job.next_run_at]
        due_jobs = self.get_due_jobs()
        runtime_up = bool(gateway.get("runtime_available"))
        scheduler_available = runtime_up
        if scheduler_available:
            msg = (
                "Gateway runtime is running — due cron jobs are executed on the gateway tick "
                "(`io gateway run`)."
            )
        else:
            msg = (
                "No gateway runtime detected. Start `io gateway run` for automatic cron ticks, "
                "or schedule `io cron tick` via cron/systemd."
            )
        return {
            "jobs_total": len(jobs),
            "jobs_enabled": len([job for job in jobs if job.enabled]),
            "jobs_due": len(due_jobs),
            "next_run_at": min(next_runs) if next_runs else None,
            "scheduler_available": scheduler_available,
            "croniter_available": HAS_CRONITER,
            "gateway": gateway,
            "message": msg,
        }
