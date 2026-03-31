"""Shared skills hub service for CLI, slash commands, and MCP."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import atomic_write_json, ensure_io_home, get_project_root
from .skills import discover_skills, inspect_skill


_GITHUB_CURATED_REPOS: tuple[tuple[str, str], ...] = (
    ("openai", "skills"),
    ("anthropics", "skills"),
    ("VoltAgent", "awesome-agent-skills"),
    ("garrytan", "gstack"),
)
_CLAWHUB_BASE_URL = "https://clawhub.ai"
_GITHUB_API_BASE = "https://api.github.com"
_MAX_TEXT_BYTES = 200_000
_ALLOWED_SUPPORT_DIRS = ("references", "templates", "scripts", "assets")
_TEXT_SCAN_EXTENSIONS = {
    ".json",
    ".js",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
_SKILL_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_DANGEROUS_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brm\s+-rf\s+/\b"), "Destructive root delete command detected."),
    (re.compile(r"\bmkfs\."), "Filesystem formatting command detected."),
    (re.compile(r"\bdd\s+if=/dev/zero"), "Disk overwrite command detected."),
    (re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:bash|sh)\b"), "Pipe-to-shell installer detected."),
    (re.compile(r"\beval\s*\("), "Dynamic eval detected."),
    (re.compile(r"\bexec\s*\("), "Dynamic exec detected."),
)
_WARN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bcurl\b"), "Network download command present."),
    (re.compile(r"\bwget\b"), "Network download command present."),
    (re.compile(r"\bnpx\s+[@\w./:-]+@latest\b"), "Floating @latest execution detected."),
    (re.compile(r"\bpip\s+install\b"), "Runtime package installation command present."),
    (re.compile(r"\bnpm\s+install\b"), "Runtime npm installation command present."),
    (re.compile(r"\bsubprocess\."), "Subprocess invocation present."),
)


class SkillsHubError(RuntimeError):
    """Raised when a hub operation cannot be completed safely."""


@dataclass(slots=True)
class HubSkillRef:
    identifier: str
    source: str
    slug: str
    name: str
    description: str
    category: str = ""
    version: str | None = None
    upstream_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass(slots=True)
class InstalledSkillRecord:
    identifier: str
    source: str
    slug: str
    name: str
    category: str
    path: str
    installed_at: float
    content_hash: str
    source_hash: str
    version: str | None = None
    upstream_url: str | None = None
    scan_verdict: str = "clean"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass(slots=True)
class ScanFinding:
    severity: str
    message: str
    path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class _HubBundle:
    ref: HubSkillRef
    files: dict[str, bytes]
    content_hash: str
    source_hash: str
    version: str | None = None
    upstream_url: str | None = None
    scan_findings: list[ScanFinding] = field(default_factory=list)
    scan_verdict: str = "clean"


def _parse_skill_text(content: str, *, default_name: str) -> tuple[str, str]:
    title = default_name
    description = ""
    name_from_frontmatter = False
    body = content
    match = _SKILL_FRONTMATTER_RE.match(content)
    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        if isinstance(frontmatter, dict):
            frontmatter_name = str(frontmatter.get("name") or "").strip()
            if frontmatter_name:
                title = frontmatter_name
                name_from_frontmatter = True
            description = str(frontmatter.get("description") or "").strip()
        body = match.group(2)
    if description:
        return title, description
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if not name_from_frontmatter:
                heading = line.lstrip("#").strip()
                if heading:
                    title = heading
            continue
        description = line
        break
    return title, description


def _normalize_bundle_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for path, payload in sorted(files.items()):
        digest.update(path.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(payload)
        digest.update(b"\x00")
    return digest.hexdigest()


def _is_text_file(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return path == "SKILL.md" or suffix in _TEXT_SCAN_EXTENSIONS


def _decode_scan_text(payload: bytes) -> str:
    sample = payload[:_MAX_TEXT_BYTES]
    return sample.decode("utf-8", errors="ignore")


class SkillsHub:
    """Hub-backed skills discovery and install service."""

    def __init__(self, *, home: Path | None = None, cwd: Path | None = None) -> None:
        self.home = ensure_io_home(home)
        self.cwd = cwd
        self.skills_dir = self.home / "skills"
        self.hub_dir = self.skills_dir / ".hub"
        self.hub_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.hub_dir / "lock.json"
        self.audit_path = self.hub_dir / "audit.log"

    def _load_lock(self) -> dict[str, Any]:
        if not self.lock_path.exists():
            return {"version": 1, "skills": {}}
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "skills": {}}
        if not isinstance(payload, dict):
            return {"version": 1, "skills": {}}
        skills = payload.get("skills")
        if not isinstance(skills, dict):
            payload["skills"] = {}
        payload.setdefault("version", 1)
        return payload

    def _save_lock(self, payload: dict[str, Any]) -> None:
        atomic_write_json(self.lock_path, payload, indent=2, sort_keys=True, chmod=0o600)

    def _append_audit(self, *, action: str, identifier: str, payload: dict[str, Any] | None = None) -> None:
        entry = {
            "timestamp": time.time(),
            "action": action,
            "identifier": identifier,
            "payload": payload or {},
        }
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")

    def _official_root(self) -> Path:
        return get_project_root() / "optional-skills"

    def _http_get_bytes(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, str], str]:
        request_headers = {
            "User-Agent": "IO-Agent/0.1.2",
            "Accept": "*/*",
        }
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read()
                headers_map = {str(key): str(value) for key, value in response.headers.items()}
                return body, headers_map, str(response.geturl())
        except urllib.error.HTTPError as exc:  # pragma: no cover - exercised via callers
            detail = exc.read().decode("utf-8", errors="ignore").strip()
            message = detail or exc.reason or str(exc)
            raise SkillsHubError(f"HTTP {exc.code} while fetching {url}: {message}") from exc
        except urllib.error.URLError as exc:  # pragma: no cover - exercised via callers
            raise SkillsHubError(f"Failed to fetch {url}: {exc.reason}") from exc

    def _http_get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        body, _headers, _resolved_url = self._http_get_bytes(url, headers=headers)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise SkillsHubError(f"Invalid JSON from {url}") from exc

    def _normalize_identifier(self, identifier: str) -> str:
        raw = str(identifier or "").strip()
        if not raw:
            raise SkillsHubError("A skill identifier is required.")
        lowered = raw.lower()
        if lowered.startswith("official/"):
            parts = [part for part in raw.split("/") if part]
            if len(parts) < 3:
                raise SkillsHubError("Official skill identifiers must be official/<category>/<slug>.")
            return "/".join(("official", parts[1].lower(), parts[2].lower()))
        if lowered.startswith("clawhub/"):
            parts = [part for part in raw.split("/") if part]
            if len(parts) < 2:
                raise SkillsHubError("ClawHub skill identifiers must be clawhub/<slug>.")
            return "/".join(("clawhub", parts[1].lower()))
        if lowered.startswith("github/"):
            parts = [part for part in raw.split("/") if part]
            if len(parts) < 5:
                raise SkillsHubError("GitHub skill identifiers must be github/<owner>/<repo>/<path>.")
            return "/".join(("github", parts[1].lower(), parts[2].lower(), *parts[3:]))
        parts = [part for part in raw.split("/") if part]
        if len(parts) >= 3:
            owner = parts[0].lower()
            repo = parts[1].lower()
            rest = "/".join(parts[2:])
            return f"github/{owner}/{repo}/{rest}"
        return raw

    def _scan_bundle(self, bundle: _HubBundle) -> tuple[str, list[ScanFinding]]:
        findings: list[ScanFinding] = []
        for path, payload in sorted(bundle.files.items()):
            if not _is_text_file(path):
                continue
            text = _decode_scan_text(payload)
            for pattern, message in _DANGEROUS_PATTERNS:
                if pattern.search(text):
                    findings.append(ScanFinding("dangerous", message, path))
            for pattern, message in _WARN_PATTERNS:
                if pattern.search(text):
                    findings.append(ScanFinding("warn", message, path))
        if bundle.ref.source == "clawhub":
            findings.extend(self._clawhub_scan_findings(bundle.ref.slug))
        verdict = "clean"
        if any(item.severity == "dangerous" for item in findings):
            verdict = "dangerous"
        elif findings:
            verdict = "warn"
        return verdict, findings

    def _record_from_lock(self, payload: dict[str, Any]) -> InstalledSkillRecord | None:
        try:
            return InstalledSkillRecord(
                identifier=str(payload["identifier"]),
                source=str(payload["source"]),
                slug=str(payload["slug"]),
                name=str(payload["name"]),
                category=str(payload.get("category") or ""),
                path=str(payload["path"]),
                installed_at=float(payload["installed_at"]),
                content_hash=str(payload["content_hash"]),
                source_hash=str(payload["source_hash"]),
                version=str(payload.get("version")) if payload.get("version") is not None else None,
                upstream_url=str(payload.get("upstream_url")) if payload.get("upstream_url") is not None else None,
                scan_verdict=str(payload.get("scan_verdict") or "clean"),
                warnings=[str(item) for item in payload.get("warnings", []) if str(item).strip()],
            )
        except (KeyError, TypeError, ValueError):
            return None

    def _save_bundle(self, bundle: _HubBundle, *, force: bool = False) -> InstalledSkillRecord:
        if bundle.scan_verdict == "dangerous":
            details = "; ".join(item.message for item in bundle.scan_findings if item.severity == "dangerous")
            raise SkillsHubError(f"Refusing to install dangerous skill: {details}")
        if bundle.scan_verdict == "warn" and not force:
            details = "; ".join(item.message for item in bundle.scan_findings if item.severity != "dangerous")
            raise SkillsHubError(f"Skill requires --force because warnings were detected: {details}")

        destination = self.skills_dir / bundle.ref.category / bundle.ref.slug if bundle.ref.category else self.skills_dir / bundle.ref.slug
        lock = self._load_lock()
        existing_record: InstalledSkillRecord | None = None
        for item in lock.get("skills", {}).values():
            if not isinstance(item, dict):
                continue
            record = self._record_from_lock(item)
            if record is not None and Path(record.path) == destination:
                existing_record = record
                break
        if destination.exists() and existing_record is None:
            raise SkillsHubError(
                f"Refusing to overwrite unmanaged local skill at {destination}."
            )

        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
        for relative_path, payload in bundle.files.items():
            target = destination / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

        warnings = [item.message for item in bundle.scan_findings if item.severity != "dangerous"]
        record = InstalledSkillRecord(
            identifier=bundle.ref.identifier,
            source=bundle.ref.source,
            slug=bundle.ref.slug,
            name=bundle.ref.name,
            category=bundle.ref.category,
            path=str(destination),
            installed_at=time.time(),
            content_hash=bundle.content_hash,
            source_hash=bundle.source_hash,
            version=bundle.version,
            upstream_url=bundle.upstream_url or bundle.ref.upstream_url,
            scan_verdict=bundle.scan_verdict,
            warnings=warnings,
        )
        lock.setdefault("skills", {})
        lock["skills"][bundle.ref.identifier] = record.to_dict()
        self._save_lock(lock)
        self._append_audit(
            action="install",
            identifier=record.identifier,
            payload={
                "path": record.path,
                "version": record.version,
                "scan_verdict": record.scan_verdict,
                "warnings": record.warnings,
            },
        )
        return record

    def _validate_relative_path(self, relative_path: str) -> None:
        normalized = Path(relative_path)
        if normalized.is_absolute():
            raise SkillsHubError(f"Absolute paths are not allowed in skill archives: {relative_path}")
        if any(part in {"", ".", ".."} for part in normalized.parts):
            raise SkillsHubError(f"Unsafe skill archive path: {relative_path}")
        if relative_path == "SKILL.md":
            return
        if normalized.parts[0] not in _ALLOWED_SUPPORT_DIRS:
            raise SkillsHubError(f"Unsupported file in skill bundle: {relative_path}")

    def _finalize_bundle(
        self,
        *,
        ref: HubSkillRef,
        files: dict[str, bytes],
        version: str | None = None,
        upstream_url: str | None = None,
        source_hash: str | None = None,
    ) -> _HubBundle:
        if "SKILL.md" not in files:
            raise SkillsHubError("Skill bundle does not contain a root SKILL.md file.")
        for path in files:
            self._validate_relative_path(path)
        if sum(1 for path in files if path == "SKILL.md") != 1:
            raise SkillsHubError("Skill bundle must contain exactly one root SKILL.md file.")
        content_hash = _normalize_bundle_hash(files)
        bundle = _HubBundle(
            ref=ref,
            files=files,
            content_hash=content_hash,
            source_hash=source_hash or content_hash,
            version=version,
            upstream_url=upstream_url or ref.upstream_url,
        )
        bundle.scan_verdict, bundle.scan_findings = self._scan_bundle(bundle)
        return bundle

    def _official_refs(self) -> list[HubSkillRef]:
        root = self._official_root()
        refs: list[HubSkillRef] = []
        if not root.exists():
            return refs
        for skill_md in sorted(root.rglob("SKILL.md")):
            skill_dir = skill_md.parent
            relative = skill_dir.relative_to(root)
            parts = list(relative.parts)
            if not parts:
                continue
            slug = parts[-1]
            category = parts[0] if len(parts) > 1 else ""
            name, description = _parse_skill_text(skill_md.read_text(encoding="utf-8"), default_name=slug)
            refs.append(
                HubSkillRef(
                    identifier=f"official/{category}/{slug}" if category else f"official/{slug}",
                    source="official",
                    slug=slug,
                    name=name,
                    description=description,
                    category=category,
                    upstream_url=str(skill_dir),
                )
            )
        return refs

    def _official_bundle(self, identifier: str) -> _HubBundle:
        normalized = self._normalize_identifier(identifier)
        if not normalized.startswith("official/"):
            raise SkillsHubError(f"Unsupported official identifier: {identifier}")
        parts = normalized.split("/")
        if len(parts) < 3:
            raise SkillsHubError("Official skill identifiers must be official/<category>/<slug>.")
        category, slug = parts[1], parts[2]
        skill_dir = self._official_root() / category / slug
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise SkillsHubError(f"Official skill not found: {normalized}")
        files: dict[str, bytes] = {}
        for path in sorted(skill_dir.rglob("*")):
            if path.is_symlink():
                raise SkillsHubError(f"Symlinks are not allowed in skill bundles: {path}")
            if path.is_dir():
                continue
            relative = str(path.relative_to(skill_dir)).replace("\\", "/")
            self._validate_relative_path(relative)
            files[relative] = path.read_bytes()
        name, description = _parse_skill_text(skill_md.read_text(encoding="utf-8"), default_name=slug)
        ref = HubSkillRef(
            identifier=normalized,
            source="official",
            slug=slug,
            name=name,
            description=description,
            category=category,
            upstream_url=str(skill_dir),
        )
        return self._finalize_bundle(ref=ref, files=files)

    def _github_tree(self, owner: str, repo: str) -> list[dict[str, Any]]:
        url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
        payload = self._http_get_json(url, headers={"Accept": "application/vnd.github+json"})
        if not isinstance(payload, dict) or not isinstance(payload.get("tree"), list):
            raise SkillsHubError(f"Invalid GitHub tree response for {owner}/{repo}")
        return [item for item in payload["tree"] if isinstance(item, dict)]

    def _github_refs(self) -> list[HubSkillRef]:
        refs: list[HubSkillRef] = []
        for owner, repo in _GITHUB_CURATED_REPOS:
            try:
                tree = self._github_tree(owner, repo)
            except SkillsHubError:
                continue
            for item in tree:
                path = str(item.get("path") or "")
                if not path.endswith("/SKILL.md"):
                    continue
                skill_root = path[: -len("/SKILL.md")]
                if not skill_root:
                    continue
                slug = skill_root.split("/")[-1].lower()
                refs.append(
                    HubSkillRef(
                        identifier=f"github/{owner.lower()}/{repo.lower()}/{skill_root}",
                        source="github",
                        slug=slug,
                        name=slug,
                        description=f"GitHub skill from {owner}/{repo}:{skill_root}",
                        category=owner.lower(),
                        upstream_url=f"https://github.com/{owner}/{repo}/tree/HEAD/{skill_root}",
                        metadata={"repo": f"{owner}/{repo}", "path": skill_root},
                    )
                )
        refs.sort(key=lambda item: item.identifier)
        return refs

    def _github_contents(self, owner: str, repo: str, path: str) -> Any:
        encoded_path = urllib.parse.quote(path.strip("/"), safe="/")
        url = f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{encoded_path}"
        return self._http_get_json(url, headers={"Accept": "application/vnd.github+json"})

    def _github_fetch_file(self, url: str) -> bytes:
        body, _headers, _resolved = self._http_get_bytes(url)
        return body

    def _github_bundle(self, identifier: str) -> _HubBundle:
        normalized = self._normalize_identifier(identifier)
        if not normalized.startswith("github/"):
            raise SkillsHubError(f"Unsupported GitHub identifier: {identifier}")
        parts = normalized.split("/")
        if len(parts) < 5:
            raise SkillsHubError("GitHub skill identifiers must be github/<owner>/<repo>/<path>.")
        owner, repo = parts[1], parts[2]
        skill_path = "/".join(parts[3:])
        root_payload = self._github_contents(owner, repo, skill_path)
        if not isinstance(root_payload, list):
            raise SkillsHubError(f"GitHub skill directory not found: {normalized}")

        files: dict[str, bytes] = {}
        pending = list(root_payload)
        while pending:
            item = pending.pop(0)
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "")
            item_path = str(item.get("path") or "")
            if item_type == "dir":
                relative_dir = item_path[len(skill_path) :].strip("/")
                if relative_dir and relative_dir.split("/", 1)[0] not in _ALLOWED_SUPPORT_DIRS:
                    continue
                child_payload = self._github_contents(owner, repo, item_path)
                if isinstance(child_payload, list):
                    pending.extend(child_payload)
                continue
            if item_type != "file":
                continue
            relative = item_path[len(skill_path) :].strip("/")
            if not relative:
                continue
            self._validate_relative_path(relative)
            download_url = str(item.get("download_url") or "")
            if download_url:
                files[relative] = self._github_fetch_file(download_url)
                continue
            content = item.get("content")
            encoding = str(item.get("encoding") or "")
            if isinstance(content, str) and encoding == "base64":
                files[relative] = base64.b64decode(content)
        if "SKILL.md" not in files:
            raise SkillsHubError(f"GitHub skill is missing SKILL.md: {normalized}")
        name, description = _parse_skill_text(
            files["SKILL.md"].decode("utf-8", errors="ignore"),
            default_name=Path(skill_path).name,
        )
        ref = HubSkillRef(
            identifier=normalized,
            source="github",
            slug=Path(skill_path).name.lower(),
            name=name,
            description=description,
            category=owner,
            upstream_url=f"https://github.com/{owner}/{repo}/tree/HEAD/{skill_path}",
            metadata={"repo": f"{owner}/{repo}", "path": skill_path},
        )
        return self._finalize_bundle(ref=ref, files=files)

    def _clawhub_refs(self, *, query: str | None = None) -> list[HubSkillRef]:
        if query:
            params = urllib.parse.urlencode({"q": query, "limit": 50})
            url = f"{_CLAWHUB_BASE_URL}/api/v1/search?{params}"
            payload = self._http_get_json(url)
            results = payload.get("results", []) if isinstance(payload, dict) else []
            refs: list[HubSkillRef] = []
            for item in results:
                if not isinstance(item, dict):
                    continue
                slug = str(item.get("slug") or "").strip().lower()
                if not slug:
                    continue
                refs.append(
                    HubSkillRef(
                        identifier=f"clawhub/{slug}",
                        source="clawhub",
                        slug=slug,
                        name=str(item.get("displayName") or slug),
                        description=str(item.get("summary") or ""),
                        category="clawhub",
                        version=str(item.get("version")) if item.get("version") is not None else None,
                        upstream_url=f"{_CLAWHUB_BASE_URL}/skills/{slug}",
                    )
                )
            return refs

        params = urllib.parse.urlencode({"limit": 100, "sort": "updated"})
        url = f"{_CLAWHUB_BASE_URL}/api/v1/skills?{params}"
        payload = self._http_get_json(url)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        refs = []
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug") or "").strip().lower()
            if not slug:
                continue
            latest = item.get("latestVersion") if isinstance(item.get("latestVersion"), dict) else {}
            refs.append(
                HubSkillRef(
                    identifier=f"clawhub/{slug}",
                    source="clawhub",
                    slug=slug,
                    name=str(item.get("displayName") or slug),
                    description=str(item.get("summary") or ""),
                    category="clawhub",
                    version=str(latest.get("version")) if latest.get("version") is not None else None,
                    upstream_url=f"{_CLAWHUB_BASE_URL}/skills/{slug}",
                    metadata={"stats": item.get("stats") if isinstance(item.get("stats"), dict) else {}},
                )
            )
        return refs

    def _clawhub_detail(self, slug: str) -> dict[str, Any]:
        payload = self._http_get_json(f"{_CLAWHUB_BASE_URL}/api/v1/skills/{slug}")
        if not isinstance(payload, dict):
            raise SkillsHubError(f"Invalid ClawHub detail response for {slug}")
        return payload

    def _clawhub_scan_findings(self, slug: str) -> list[ScanFinding]:
        try:
            payload = self._http_get_json(f"{_CLAWHUB_BASE_URL}/api/v1/skills/{slug}/scan?tag=latest")
        except SkillsHubError:
            return []
        if not isinstance(payload, dict):
            return []
        findings: list[ScanFinding] = []
        moderation = payload.get("moderation") if isinstance(payload.get("moderation"), dict) else {}
        summary = str(moderation.get("summary") or "").strip()
        verdict = str(moderation.get("verdict") or "").strip().lower()
        if verdict in {"malicious"}:
            findings.append(ScanFinding("dangerous", summary or "Registry reported malicious verdict.", "registry"))
        elif verdict in {"suspicious"}:
            findings.append(ScanFinding("warn", summary or "Registry reported suspicious verdict.", "registry"))
        security = payload.get("security") if isinstance(payload.get("security"), dict) else {}
        verification = str(security.get("verificationStatus") or "").strip().lower()
        if verification in {"malicious", "blocked"}:
            findings.append(ScanFinding("dangerous", "Registry security scan blocked this release.", "registry"))
        elif verification in {"suspicious", "warn"}:
            findings.append(ScanFinding("warn", "Registry security scan marked this release suspicious.", "registry"))
        return findings

    def _clawhub_bundle(self, identifier: str) -> _HubBundle:
        normalized = self._normalize_identifier(identifier)
        if not normalized.startswith("clawhub/"):
            raise SkillsHubError(f"Unsupported ClawHub identifier: {identifier}")
        slug = normalized.split("/", 1)[1]
        detail = self._clawhub_detail(slug)
        latest = detail.get("latestVersion") if isinstance(detail.get("latestVersion"), dict) else {}
        version = str(latest.get("version")) if latest.get("version") is not None else None
        download_params = {"slug": slug}
        if version:
            download_params["version"] = version
        url = f"{_CLAWHUB_BASE_URL}/api/v1/download?{urllib.parse.urlencode(download_params)}"
        archive_bytes, _headers, resolved_url = self._http_get_bytes(url)
        files: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            for info in archive.infolist():
                relative_parts = Path(info.filename).parts
                if not relative_parts or info.is_dir():
                    continue
                if info.filename.startswith("/") or ".." in relative_parts:
                    raise SkillsHubError(f"Unsafe path in ClawHub archive: {info.filename}")
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise SkillsHubError(f"Symlink entry is not allowed: {info.filename}")
                relative = "/".join(relative_parts[1:]) if len(relative_parts) > 1 else relative_parts[0]
                if not relative:
                    continue
                self._validate_relative_path(relative)
                files[relative] = archive.read(info)
        if "SKILL.md" not in files:
            raise SkillsHubError(f"Downloaded ClawHub skill archive is missing SKILL.md: {slug}")
        skill_text = files["SKILL.md"].decode("utf-8", errors="ignore")
        name, description = _parse_skill_text(skill_text, default_name=slug)
        ref = HubSkillRef(
            identifier=normalized,
            source="clawhub",
            slug=slug,
            name=name or str(detail.get("skill", {}).get("displayName") or slug),
            description=description or str(detail.get("skill", {}).get("summary") or ""),
            category="clawhub",
            version=version,
            upstream_url=f"{_CLAWHUB_BASE_URL}/skills/{slug}",
            metadata={"detail": detail},
        )
        source_hash = hashlib.sha256(archive_bytes).hexdigest()
        return self._finalize_bundle(ref=ref, files=files, version=version, upstream_url=resolved_url, source_hash=source_hash)

    def _bundle_for_identifier(self, identifier: str) -> _HubBundle:
        normalized = self._normalize_identifier(identifier)
        if normalized.startswith("official/"):
            return self._official_bundle(normalized)
        if normalized.startswith("github/"):
            return self._github_bundle(normalized)
        if normalized.startswith("clawhub/"):
            return self._clawhub_bundle(normalized)
        raise SkillsHubError(f"Unknown hub identifier: {identifier}")

    def browse(self, *, source: str = "all") -> dict[str, Any]:
        normalized = str(source or "all").strip().lower() or "all"
        skills: list[HubSkillRef] = []
        if normalized in {"all", "official"}:
            skills.extend(self._official_refs())
        if normalized in {"all", "github"}:
            skills.extend(self._github_refs())
        if normalized in {"all", "clawhub"}:
            skills.extend(self._clawhub_refs())
        return {
            "success": True,
            "source": normalized,
            "skills": [item.to_dict() for item in sorted(skills, key=lambda item: item.identifier)],
            "count": len(skills),
        }

    def search(self, query: str, *, source: str = "all") -> dict[str, Any]:
        needle = str(query or "").strip()
        if not needle:
            raise SkillsHubError("A search query is required.")
        normalized = str(source or "all").strip().lower() or "all"
        skills: list[HubSkillRef] = []
        if normalized in {"all", "official"}:
            skills.extend(self._official_refs())
        if normalized in {"all", "github"}:
            skills.extend(self._github_refs())
        if normalized in {"all", "clawhub"}:
            skills.extend(self._clawhub_refs(query=needle))
        lowered = needle.lower()
        deduped: dict[str, HubSkillRef] = {}
        for item in skills:
            haystack = "\n".join((item.identifier, item.name, item.description, item.category)).lower()
            if lowered in haystack:
                deduped[item.identifier] = item
        return {
            "success": True,
            "query": needle,
            "source": normalized,
            "skills": [item.to_dict() for item in sorted(deduped.values(), key=lambda item: item.identifier)],
            "count": len(deduped),
        }

    def inspect(self, identifier: str) -> dict[str, Any]:
        normalized = self._normalize_identifier(identifier)
        if normalized.startswith(("official/", "github/", "clawhub/")):
            bundle = self._bundle_for_identifier(normalized)
            skill_text = bundle.files["SKILL.md"].decode("utf-8", errors="ignore")
            return {
                "success": True,
                "identifier": bundle.ref.identifier,
                "source": bundle.ref.source,
                "skill": bundle.ref.to_dict(),
                "content": skill_text,
                "files": sorted(bundle.files),
                "scan_verdict": bundle.scan_verdict,
                "scan_findings": [item.to_dict() for item in bundle.scan_findings],
                "installed": self._load_lock().get("skills", {}).get(bundle.ref.identifier),
            }
        local = inspect_skill(identifier, home=self.home, cwd=self.cwd)
        return {
            "success": True,
            "identifier": identifier,
            "source": "local",
            "skill": local,
            "content": str(local.get("content") or ""),
            "files": sorted(str(path) for paths in local.get("linked_files", {}).values() for path in paths),
            "scan_verdict": "clean",
            "scan_findings": [],
            "installed": None,
        }

    def install(self, identifier: str, *, force: bool = False) -> dict[str, Any]:
        bundle = self._bundle_for_identifier(identifier)
        record = self._save_bundle(bundle, force=force)
        return {
            "success": True,
            "installed": record.to_dict(),
            "scan_findings": [item.to_dict() for item in bundle.scan_findings],
        }

    def list_installed(self) -> dict[str, Any]:
        lock = self._load_lock()
        records: list[InstalledSkillRecord] = []
        for item in lock.get("skills", {}).values():
            if not isinstance(item, dict):
                continue
            record = self._record_from_lock(item)
            if record is not None:
                records.append(record)
        records.sort(key=lambda item: item.identifier)
        return {
            "success": True,
            "skills": [item.to_dict() for item in records],
            "count": len(records),
        }

    def uninstall(self, identifier: str) -> dict[str, Any]:
        lock = self._load_lock()
        normalized = self._normalize_identifier(identifier)
        target_key = normalized if normalized in lock.get("skills", {}) else None
        if target_key is None:
            for key, payload in lock.get("skills", {}).items():
                if not isinstance(payload, dict):
                    continue
                if str(payload.get("slug") or "") == identifier or str(payload.get("name") or "") == identifier:
                    target_key = key
                    break
        if target_key is None:
            raise SkillsHubError(f"Hub-managed skill not found: {identifier}")
        record = self._record_from_lock(lock["skills"][target_key])
        if record is None:
            raise SkillsHubError(f"Hub-managed skill metadata is invalid: {identifier}")
        target_path = Path(record.path)
        if target_path.exists():
            shutil.rmtree(target_path)
        lock["skills"].pop(target_key, None)
        self._save_lock(lock)
        self._append_audit(action="uninstall", identifier=record.identifier, payload={"path": record.path})
        return {
            "success": True,
            "identifier": record.identifier,
            "path": record.path,
        }

    def check_updates(self, identifier: str | None = None) -> dict[str, Any]:
        lock = self._load_lock()
        records: list[InstalledSkillRecord] = []
        for key, payload in lock.get("skills", {}).items():
            if not isinstance(payload, dict):
                continue
            record = self._record_from_lock(payload)
            if record is None:
                continue
            if identifier is not None:
                normalized = self._normalize_identifier(identifier)
                if key != normalized and record.slug != identifier and record.name != identifier:
                    continue
            records.append(record)
        updates: list[dict[str, Any]] = []
        for record in records:
            try:
                bundle = self._bundle_for_identifier(record.identifier)
            except SkillsHubError as exc:
                updates.append(
                    {
                        "identifier": record.identifier,
                        "status": "error",
                        "error": str(exc),
                    }
                )
                continue
            changed = bundle.source_hash != record.source_hash or bundle.content_hash != record.content_hash
            updates.append(
                {
                    "identifier": record.identifier,
                    "status": "update_available" if changed else "up_to_date",
                    "installed_version": record.version,
                    "latest_version": bundle.version,
                    "scan_verdict": bundle.scan_verdict,
                }
            )
        return {
            "success": True,
            "updates": updates,
            "count": len(updates),
        }

    def list_local_skills(self) -> dict[str, Any]:
        skills = [skill.to_dict() for skill in discover_skills(home=self.home, cwd=self.cwd, platform="cli")]
        return {"success": True, "skills": skills, "count": len(skills)}


def format_skills_hub_output(payload: dict[str, Any]) -> str:
    if not payload.get("success"):
        return str(payload.get("error") or "Skill command failed.")
    if "installed_hub" in payload and "skills" in payload:
        local_rows = payload.get("skills", [])
        hub_rows = payload.get("installed_hub", [])
        lines = [
            f"Local skills: {len(local_rows)}",
            f"Hub-managed installs: {len(hub_rows)}",
        ]
        if local_rows:
            lines.append("")
            lines.append("Local:")
            for item in local_rows[:10]:
                if not isinstance(item, dict):
                    continue
                lines.append(f"- {item.get('name') or item.get('identifier')}")
        if hub_rows:
            lines.append("")
            lines.append("Hub:")
            for item in hub_rows[:10]:
                if not isinstance(item, dict):
                    continue
                lines.append(f"- {item.get('identifier') or item.get('name')}")
        return "\n".join(lines)
    if "installed" in payload:
        record = payload.get("installed", {})
        findings = payload.get("scan_findings", [])
        lines = [
            f"Installed {record.get('identifier')} -> {record.get('path')}",
        ]
        if record.get("version"):
            lines.append(f"Version: {record.get('version')}")
        if findings:
            lines.append("Warnings:")
            for item in findings:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('severity')}: {item.get('message')} ({item.get('path')})")
        return "\n".join(lines)
    if "updates" in payload:
        rows = payload.get("updates", [])
        if not rows:
            return "No hub-managed skills are installed."
        lines = ["Hub update status:"]
        for item in rows:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "unknown")
            lines.append(f"- {item.get('identifier')}: {status}")
        return "\n".join(lines)
    if "skills" in payload:
        rows = payload.get("skills", [])
        if not rows:
            return "No matching skills found."
        lines = []
        if "query" in payload:
            lines.append(f"Skill search results for '{payload.get('query')}':")
        elif payload.get("source") in {"hub", "local", "all"}:
            lines.append("Installed skills:")
        else:
            lines.append("Available skills:")
        for item in rows[:20]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("identifier") or item.get("name") or "skill")
            description = str(item.get("description") or item.get("summary") or "").strip()
            suffix = f" — {description}" if description else ""
            lines.append(f"- {label}{suffix}")
        if len(rows) > 20:
            lines.append(f"... and {len(rows) - 20} more")
        return "\n".join(lines)
    if "content" in payload and isinstance(payload.get("content"), str):
        skill = payload.get("skill") if isinstance(payload.get("skill"), dict) else {}
        lines = [
            f"{payload.get('identifier')}",
            f"Source: {payload.get('source')}",
        ]
        description = str(skill.get("description") or "").strip()
        if description:
            lines.append(description)
        lines.extend(["", str(payload["content"])[:4000]])
        return "\n".join(lines)
    return json.dumps(payload, indent=2, sort_keys=True)


def run_skills_hub_command(
    command: str,
    *,
    home: Path,
    cwd: Path,
) -> dict[str, Any]:
    service = SkillsHub(home=home, cwd=cwd)
    parts = command.strip().split()
    if not parts:
        return {
            "success": True,
            "message": (
                "Usage: /skills browse|search <query>|inspect <identifier>|install <identifier> "
                "[--force]|list|uninstall <identifier>|check [identifier]"
            ),
        }
    subcommand = parts[0].lower()
    args = parts[1:]

    if subcommand == "browse":
        source = "all"
        if len(args) >= 2 and args[0] == "--source":
            source = args[1]
        return service.browse(source=source)
    if subcommand == "search":
        source = "all"
        query_parts = list(args)
        if len(query_parts) >= 2 and query_parts[-2] == "--source":
            source = query_parts[-1]
            query_parts = query_parts[:-2]
        return service.search(" ".join(query_parts), source=source)
    if subcommand == "inspect":
        return service.inspect(" ".join(args))
    if subcommand == "install":
        force = "--force" in args
        identifier_parts = [item for item in args if item != "--force"]
        return service.install(" ".join(identifier_parts), force=force)
    if subcommand == "list":
        source = "local"
        if len(args) >= 2 and args[0] == "--source":
            source = args[1]
        normalized = source.strip().lower()
        if normalized == "local":
            return service.list_local_skills()
        if normalized == "hub":
            return service.list_installed()
        if normalized == "all":
            return {
                "success": True,
                "skills": service.list_local_skills()["skills"],
                "installed_hub": service.list_installed()["skills"],
            }
        raise SkillsHubError(f"Unsupported list source: {source}")
    if subcommand == "uninstall":
        return service.uninstall(" ".join(args))
    if subcommand == "check":
        return service.check_updates(" ".join(args).strip() or None)
    raise SkillsHubError(f"Unknown /skills subcommand: {subcommand}")
