from __future__ import annotations

from pathlib import Path

from io_cli.cron import CronManager
from io_cli.gateway import GatewayManager
from io_cli.gateway_runtime import write_pid_file, write_runtime_status
from io_cli.gateway_session import SessionSource, build_session_context_prompt
from io_cli.gateway_models import Platform


def test_gateway_manager_persists_configuration(tmp_path: Path) -> None:
    manager = GatewayManager(home=tmp_path / "home")
    manager.configure(platforms=["slack", "telegram"], home_channel="ops-room")
    manager.install(scope="user")
    status = manager.status()
    assert "slack" in status["configured_platforms"]
    assert status["home_channel"] == "ops-room"
    assert "user" in status["installed_scopes"]
    assert "telegram" in status["home_channels"]


def test_gateway_manager_merges_runtime_snapshot(tmp_path: Path) -> None:
    home = tmp_path / "home"
    manager = GatewayManager(home=home)
    write_pid_file(manager.home)
    write_runtime_status(manager.home, gateway_state="running", platform="telegram", platform_state="connected")

    status = manager.status()

    assert status["runtime_available"] is True
    assert status["runtime"]["gateway_state"] == "running"
    assert status["runtime"]["platforms"]["telegram"]["state"] == "connected"


def test_gateway_manager_builds_session_context(tmp_path: Path) -> None:
    manager = GatewayManager(home=tmp_path / "home")
    manager.configure(platforms=["telegram"], home_channel="home-chat")

    context = manager.build_session_context(
        SessionSource(
            platform=Platform.TELEGRAM,
            chat_id="12345",
            chat_name="Ops",
            user_id="u-1",
            user_name="Ever",
            chat_type="dm",
        )
    )

    assert context.source.chat_id == "12345"
    assert context.session_key.startswith("agent:main:telegram:dm:")
    assert context.session_id
    prompt = build_session_context_prompt(context)
    assert "Delivery options for scheduled tasks" in prompt
    assert '`"telegram"` -> Home channel' in prompt


def test_cron_manager_create_and_run_job(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    (cwd / "alpha.txt").write_text("hello", encoding="utf-8")
    manager = CronManager(home=tmp_path / "home")
    job = manager.create_job(
        prompt='TOOL[ls] {"path": "."}',
        schedule="manual",
        cwd=cwd,
        name="List repo",
    )
    result = manager.run_job_sync(job["id"], model="mock/io-test", provider="mock")
    assert "alpha.txt" in str(result["result"])
    assert result["last_session_path"] is not None


def test_cron_manager_parses_oneshot_schedule(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    manager = CronManager(home=tmp_path / "home")

    job = manager.create_job(
        prompt="say hello",
        schedule="30m",
        cwd=cwd,
        name="One shot",
    )

    assert job["schedule"]["kind"] == "once"
    assert job["repeat"]["times"] == 1
    assert job["next_run_at"] is not None


def test_cron_manager_tick_runs_only_due_jobs_and_saves_output(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    (cwd / "alpha.txt").write_text("hello", encoding="utf-8")
    manager = CronManager(home=tmp_path / "home")

    interval_job = manager.create_job(
        prompt='TOOL[ls] {"path": "."}',
        schedule="every 30m",
        cwd=cwd,
        name="Interval list",
    )

    assert manager.tick_sync(model="mock/io-test", provider="mock") == []

    manager.trigger_job(interval_job["id"])
    results = manager.tick_sync(model="mock/io-test", provider="mock")

    assert len(results) == 1
    assert "alpha.txt" in str(results[0]["result"])
    assert Path(results[0]["output_path"]).exists()


def test_cron_manager_status_reports_next_run(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    manager = CronManager(home=tmp_path / "home")
    manager.create_job(
        prompt="say hello",
        schedule="every 2h",
        cwd=cwd,
        name="Status job",
    )

    status = manager.status()

    assert status["jobs_total"] == 1
    assert status["jobs_enabled"] == 1
    assert status["jobs_due"] == 0
    assert status["next_run_at"] is not None
