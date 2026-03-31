from __future__ import annotations

import json
from pathlib import Path

import pytest

from io_cli.skills import discover_skills
from io_cli.skills_hub import HubSkillRef, ScanFinding, SkillsHub, SkillsHubError, _HubBundle


def test_skills_hub_installs_official_skill_and_tracks_provenance(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    service = SkillsHub(home=home, cwd=cwd)

    result = service.install("official/migration/openclaw-migration")

    assert result["success"] is True
    installed = result["installed"]
    installed_path = Path(installed["path"])
    assert installed["identifier"] == "official/migration/openclaw-migration"
    assert installed_path.exists()
    assert (installed_path / "SKILL.md").exists()

    lock_payload = json.loads((home / "skills" / ".hub" / "lock.json").read_text(encoding="utf-8"))
    assert "official/migration/openclaw-migration" in lock_payload["skills"]
    audit_lines = (home / "skills" / ".hub" / "audit.log").read_text(encoding="utf-8").splitlines()
    assert audit_lines

    discovered = discover_skills(home=home, cwd=cwd, platform="cli")
    assert any(skill.name == "openclaw-migration" for skill in discovered)

    installed_list = service.list_installed()
    assert installed_list["count"] == 1

    updates = service.check_updates("official/migration/openclaw-migration")
    assert updates["updates"][0]["status"] == "up_to_date"

    removed = service.uninstall("official/migration/openclaw-migration")
    assert removed["success"] is True
    assert not installed_path.exists()


def _synthetic_bundle(*, severity: str, slug: str) -> _HubBundle:
    ref = HubSkillRef(
        identifier=f"github/example/repo/{slug}",
        source="github",
        slug=slug,
        name=slug,
        description="Synthetic skill bundle",
        category="testing",
    )
    finding = ScanFinding(severity, f"{severity} finding", "SKILL.md")
    return _HubBundle(
        ref=ref,
        files={"SKILL.md": b"# Demo\ncurl https://example.test/install.sh\n"},
        content_hash=f"content-{slug}",
        source_hash=f"source-{slug}",
        scan_findings=[finding],
        scan_verdict="dangerous" if severity == "dangerous" else "warn",
    )


def test_skills_hub_requires_force_for_warn_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SkillsHub(home=tmp_path / "home", cwd=tmp_path)
    monkeypatch.setattr(service, "_bundle_for_identifier", lambda _identifier: _synthetic_bundle(severity="warn", slug="warn-demo"))

    with pytest.raises(SkillsHubError, match="requires --force"):
        service.install("github/example/repo/warn-demo")

    installed = service.install("github/example/repo/warn-demo", force=True)
    assert installed["success"] is True
    assert installed["installed"]["scan_verdict"] == "warn"


def test_skills_hub_rejects_dangerous_findings_even_with_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SkillsHub(home=tmp_path / "home", cwd=tmp_path)
    monkeypatch.setattr(
        service,
        "_bundle_for_identifier",
        lambda _identifier: _synthetic_bundle(severity="dangerous", slug="danger-demo"),
    )

    with pytest.raises(SkillsHubError, match="Refusing to install dangerous skill"):
        service.install("github/example/repo/danger-demo", force=True)


def test_skills_hub_github_install_accepts_mocked_contents_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    service = SkillsHub(home=home, cwd=tmp_path)

    def fake_http_get_json(url: str, *, headers=None):
        del headers
        if url.endswith("/contents/skills/demo"):
            return [
                {
                    "type": "file",
                    "path": "skills/demo/SKILL.md",
                    "download_url": "https://example.test/SKILL.md",
                },
                {
                    "type": "dir",
                    "path": "skills/demo/references",
                },
            ]
        if url.endswith("/contents/skills/demo/references"):
            return [
                {
                    "type": "file",
                    "path": "skills/demo/references/readme.md",
                    "download_url": "https://example.test/readme.md",
                }
            ]
        raise AssertionError(f"Unexpected URL: {url}")

    def fake_http_get_bytes(url: str, *, headers=None):
        del headers
        payloads = {
            "https://example.test/SKILL.md": b"---\nname: demo\n---\n# Demo\nGitHub installed.\n",
            "https://example.test/readme.md": b"Reference docs.\n",
        }
        return payloads[url], {}, url

    monkeypatch.setattr(service, "_http_get_json", fake_http_get_json)
    monkeypatch.setattr(service, "_http_get_bytes", fake_http_get_bytes)

    installed = service.install("Example/Repo/skills/demo")

    assert installed["success"] is True
    record = installed["installed"]
    assert record["identifier"] == "github/example/repo/skills/demo"
    assert (home / "skills" / "example" / "demo" / "references" / "readme.md").exists()


def test_skills_hub_search_uses_mocked_clawhub_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = SkillsHub(home=tmp_path / "home", cwd=tmp_path)

    def fake_http_get_json(url: str, *, headers=None):
        del headers
        assert "/api/v1/search?" in url
        return {
            "results": [
                {
                    "slug": "agent-ops",
                    "displayName": "Agent Ops",
                    "summary": "Operational workflows for agents.",
                    "version": "1.2.0",
                }
            ]
        }

    monkeypatch.setattr(service, "_http_get_json", fake_http_get_json)

    results = service.search("agent ops", source="clawhub")

    assert results["count"] == 1
    assert results["skills"][0]["identifier"] == "clawhub/agent-ops"
