"""Safe, user-confirmed update checks for MSH client review builds."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_UPDATE_MANIFEST_URL = (
    "https://raw.githubusercontent.com/cioudio931105-maker/MSH-Releases/main/latest.json"
)
_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_MAX_MANIFEST_BYTES = 256 * 1024


class UpdateCheckError(RuntimeError):
    """An update manifest could not be downloaded or validated."""


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    release_name: str
    release_notes: str
    download_url: str
    release_page_url: str
    sha256: str
    published_at: str


def _require_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"更新資訊缺少有效欄位：{field}")
    return value.strip()


def _require_https_url(payload: dict[str, Any], field: str) -> str:
    value = _require_text(payload, field)
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"更新資訊的 {field} 必須是 HTTPS 網址")
    return value


def _semantic_key(version: str) -> tuple[Any, ...]:
    match = _SEMVER_RE.fullmatch(version.strip())
    if match is None:
        raise ValueError(f"無效的版本格式：{version}")
    prerelease = match.group("prerelease")
    prerelease_key: tuple[tuple[int, Any], ...] = ()
    if prerelease is not None:
        prerelease_key = tuple(
            (0, int(part)) if part.isdigit() else (1, part.lower())
            for part in prerelease.split(".")
        )
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        1 if prerelease is None else 0,
        prerelease_key,
    )


def is_newer_version(candidate: str, current: str) -> bool:
    """Return whether candidate has greater Semantic Version precedence."""

    return _semantic_key(candidate) > _semantic_key(current)


def parse_update_manifest(payload: dict[str, Any]) -> UpdateManifest:
    """Validate untrusted JSON data before it reaches the GUI."""

    if payload.get("schema_version") != 1:
        raise ValueError("不支援的更新資訊格式")
    version = _require_text(payload, "version")
    _semantic_key(version)
    sha256 = _require_text(payload, "sha256").lower()
    if _SHA256_RE.fullmatch(sha256) is None:
        raise ValueError("更新資訊的 sha256 必須是 64 位十六進位值")
    return UpdateManifest(
        version=version,
        release_name=_require_text(payload, "release_name"),
        release_notes=_require_text(payload, "release_notes"),
        download_url=_require_https_url(payload, "download_url"),
        release_page_url=_require_https_url(payload, "release_page_url"),
        sha256=sha256,
        published_at=_require_text(payload, "published_at"),
    )


def fetch_update_manifest(
    manifest_url: str = DEFAULT_UPDATE_MANIFEST_URL,
    *,
    timeout: float = 8.0,
) -> UpdateManifest:
    """Download and validate a small public update manifest over HTTPS."""

    parsed_url = urlparse(manifest_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise UpdateCheckError("更新資訊網址必須使用 HTTPS")
    request = Request(
        manifest_url,
        headers={"Accept": "application/json", "User-Agent": "MSH-Update-Checker/1"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(_MAX_MANIFEST_BYTES + 1)
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise UpdateCheckError(f"無法取得更新資訊：{exc}") from exc
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise UpdateCheckError("更新資訊檔案過大")
    try:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("更新資訊必須是 JSON 物件")
        return parse_update_manifest(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise UpdateCheckError(f"更新資訊格式無效：{exc}") from exc


def check_for_update(
    current_version: str,
    manifest_url: str = DEFAULT_UPDATE_MANIFEST_URL,
    *,
    timeout: float = 8.0,
) -> UpdateManifest | None:
    """Return the validated manifest only when it is newer than MSH."""

    manifest = fetch_update_manifest(manifest_url, timeout=timeout)
    return manifest if is_newer_version(manifest.version, current_version) else None
