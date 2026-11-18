"""Safe, user-confirmed update checks for MSH client review builds."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


DEFAULT_UPDATE_MANIFEST_URL = (
    "https://raw.githubusercontent.com/cioudio931105-maker/MSH-Releases/main/latest.json"
)
RELEASE_REPOSITORY = "cioudio931105-maker/MSH-Releases"
MAX_INSTALLER_BYTES = 12 * 1024**3
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
    size_bytes: int | None = None


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
    size = payload.get("size_bytes")
    if size is not None and (type(size) is not int or not 0 < size <= MAX_INSTALLER_BYTES):
        raise ValueError("更新資訊的 size_bytes 無效")
    return UpdateManifest(
        version=version,
        release_name=_require_text(payload, "release_name"),
        release_notes=_require_text(payload, "release_notes"),
        download_url=_require_https_url(payload, "download_url"),
        release_page_url=_require_https_url(payload, "release_page_url"),
        sha256=sha256,
        published_at=_require_text(payload, "published_at"),
        size_bytes=size,
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


class DownloadCancelled(UpdateCheckError):
    """The user cancelled a download; the installed version is unchanged."""


def validate_installer_url(url: str) -> str:
    """Only execute installers published under the configured repository."""
    parsed = urlparse(url)
    prefix = f"/{RELEASE_REPOSITORY}/releases/download/"
    remainder = parsed.path[len(prefix):] if parsed.path.startswith(prefix) else ""
    parts = remainder.split("/")
    if (parsed.scheme != "https" or parsed.hostname != "github.com"
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or not parsed.path.startswith(prefix) or not parsed.path.lower().endswith(".exe")
            or parsed.fragment or parsed.query or len(parts) != 2
            or any(part in {"", ".", ".."} or "%" in part for part in parts)):
        raise UpdateCheckError("安裝檔必須來自 MSH 官方 repository 的 HTTPS Release 下載網址。")
    return url


def _validate_download_host(url: str) -> None:
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname not in {
            "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise UpdateCheckError("下載被導向未核准的來源，已停止更新。")


class _ReleaseRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_download_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def verify_installer(path: Path, sha256: str, size_bytes: int | None = None) -> None:
    """Recheck cached bytes immediately before installer handoff."""
    digest = hashlib.sha256()
    count = 0
    try:
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise UpdateCheckError("下載內容不是 Windows 安裝程式。")
            stream.seek(0)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                count += len(chunk)
                if count > MAX_INSTALLER_BYTES:
                    raise UpdateCheckError("安裝檔超過允許大小。")
                digest.update(chunk)
    except OSError as exc:
        raise UpdateCheckError("無法讀取已下載的安裝檔。") from exc
    if size_bytes is not None and count != size_bytes:
        raise UpdateCheckError("安裝檔大小不符，請重新下載。")
    if not _SHA256_RE.fullmatch(sha256) or digest.hexdigest() != sha256.lower():
        raise UpdateCheckError("安裝檔 SHA-256 不符，已停止更新。")


def download_installer(
    manifest: UpdateManifest, destination: Path, *,
    cancel: threading.Event | None = None,
    progress: Callable[[int, int | None], None] | None = None,
    timeout: float = 20.0,
) -> Path:
    """Stream into a unique partial file, then atomically expose verified bytes."""
    validate_installer_url(manifest.download_url)
    _semantic_key(manifest.version)
    if not _SHA256_RE.fullmatch(manifest.sha256):
        raise UpdateCheckError("更新資訊的 sha256 無效。")
    destination.mkdir(parents=True, exist_ok=True)
    # A digest-derived name prevents traversal or collisions from remote filenames.
    target = destination / f"MSH_Update_{manifest.sha256.lower()}.exe"
    partial = destination / f"{uuid.uuid4().hex}.part"
    started = time.monotonic()
    try:
        if cancel is not None and cancel.is_set():
            raise DownloadCancelled("已取消下載。")
        request = Request(manifest.download_url, headers={"User-Agent": "MSH-Updater/1"})
        with build_opener(_ReleaseRedirectHandler()).open(request, timeout=timeout) as response:
            _validate_download_host(response.geturl())
            header = response.headers.get("Content-Length")
            total = int(header) if header else manifest.size_bytes
            if total is not None and not 0 < total <= MAX_INSTALLER_BYTES:
                raise UpdateCheckError("下載大小無效。")
            if manifest.size_bytes is not None and total != manifest.size_bytes:
                raise UpdateCheckError("下載大小與更新資訊不符。")
            count = 0
            with partial.open("xb") as stream:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise DownloadCancelled("已取消下載，既有版本保持不變。")
                    if time.monotonic() - started > 3600:
                        raise UpdateCheckError("下載逾時，請稍後重試。")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    count += len(chunk)
                    if count > MAX_INSTALLER_BYTES or (total is not None and count > total):
                        raise UpdateCheckError("下載內容超過預期大小。")
                    stream.write(chunk)
                    if progress is not None:
                        progress(count, total)
            if total is not None and count != total:
                raise UpdateCheckError("下載未完成，請重新下載。")
        if cancel is not None and cancel.is_set():
            raise DownloadCancelled("已取消下載。")
        verify_installer(partial, manifest.sha256, manifest.size_bytes)
        os.replace(partial, target)
        return target
    except UpdateCheckError:
        raise
    except (OSError, ValueError, HTTPError, URLError, HTTPException) as exc:
        raise UpdateCheckError(f"下載失敗；目前版本保持不變：{exc}") from exc
    finally:
        partial.unlink(missing_ok=True)
