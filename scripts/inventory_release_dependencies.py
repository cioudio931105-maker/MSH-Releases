"""Offline native-payload provenance inventory; this is not license clearance or an SBOM."""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import re


NATIVE_SUFFIXES = {".dll", ".pyd", ".exe"}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(payload: Path, distributions=None) -> dict:
    """Compare payload bytes with RECORD-owned installed files without importing libraries."""
    if not payload.is_dir():
        raise NotADirectoryError(payload)
    natives = sorted(p for p in payload.rglob("*") if p.is_file() and p.suffix.lower() in NATIVE_SUFFIXES)
    names = {p.name.lower() for p in natives}
    by_name = defaultdict(list)
    packages = []
    digests = {}
    installed = metadata.distributions() if distributions is None else distributions
    for dist in sorted(installed, key=lambda d: d.metadata["Name"].lower()):
        name, version = dist.metadata["Name"], dist.version
        files = list(dist.files or [])
        notices = [p.as_posix() for p in files if re.match(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)([._-].*)?$", p.name, re.I)]
        packages.append({
            "name": name, "version": version,
            "license_expression": dist.metadata.get("License-Expression"),
            "project_urls": dist.metadata.get_all("Project-URL") or [],
            "homepage": dist.metadata.get("Home-page"),
            "notice_record_paths": sorted(notices),
        })
        for relative in files:
            if relative.name.lower() not in names or relative.suffix.lower() not in NATIVE_SUFFIXES:
                continue
            source = Path(dist.locate_file(relative))
            if not source.is_file():
                continue
            key = source.resolve()
            if key not in digests:
                digests[key] = sha256(source)
            digest = digests[key]
            recorded = relative.hash
            record_matches = None
            if recorded and recorded.mode == "sha256":
                encoded = base64.urlsafe_b64encode(bytes.fromhex(digest)).decode().rstrip("=")
                record_matches = encoded == recorded.value
            by_name[relative.name.lower()].append({
                "distribution": name, "version": version,
                "record_path": relative.as_posix(), "installed_sha256": digest,
                "installed_matches_record_sha256": record_matches,
            })
    rows = []
    for path in natives:
        digest = sha256(path)
        claims = by_name[path.name.lower()]
        matches = [c for c in claims if c["installed_sha256"] == digest]
        rows.append({
            "path": path.relative_to(payload).as_posix(), "bytes": path.stat().st_size,
            "sha256": digest, "matching_installed_owners": matches,
            "status": "exact_installed_match" if matches else "unresolved",
            "same_name_nonmatching_owners": [c for c in claims if c["installed_sha256"] != digest],
        })
    owners = Counter(c["distribution"] for row in rows for c in row["matching_installed_owners"])
    return {
        "schema_version": 1,
        "scope": "Native files only; installed environment metadata is not proof of frozen Python membership. No imports or network operations performed.",
        "python_version": platform.python_version(),
        "summary": {
            "installed_distributions": len(packages), "native_payload_files": len(rows),
            "exact_installed_matches": sum(bool(r["matching_installed_owners"]) for r in rows),
            "unresolved_native_files": sum(not r["matching_installed_owners"] for r in rows),
            "matched_owner_claims": dict(sorted(owners.items())),
        },
        "installed_environment": packages, "native_payload": rows,
        "limitations": [
            "Matching bytes establish provenance evidence, not redistribution rights or complete corresponding source.",
            "Unresolved may include the application, Python/Conda/Tcl/Tk/system files or transformed binaries; review individually.",
            "Overlapping distribution RECORDs are retained as multiple claims, including RECORD hash mismatches.",
            "Project URLs are unverified package metadata, not verified version-specific source archives.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite: {args.output}")
    report = inventory(args.payload)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    print(json.dumps(report["summary"], indent=2))
    print("Inventory only; unresolved provenance and license/source obligations require review.")


if __name__ == "__main__":
    main()
