"""Copy original text notices for explicitly selected Conda runtime packages."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def collect(prefix: Path, destination: Path, packages: list[str]) -> int:
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite: {destination}")
    selected = set(packages)
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", name) for name in selected):
        raise ValueError("Invalid package name")
    records = {}
    for path in sorted((prefix / "conda-meta").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["name"] in selected:
            if record["name"] in records:
                raise ValueError(f"Multiple installed records: {record['name']}")
            records[record["name"]] = record
    if selected != set(records):
        raise ValueError(f"Missing package records: {sorted(selected - set(records))}")
    notices = []
    for name, record in sorted(records.items()):
        cache = Path(record["extracted_package_dir"]) / "info"
        candidates = [(path, f"package cache: {path.relative_to(cache).as_posix()}")
                      for path in sorted((cache / "licenses").rglob("*")) if path.is_file()]
        if name == "tk":
            path = prefix / "Library/lib/tk8.6/license.terms"
            if path.is_file():
                candidates.append((path, "runtime prefix: Library/lib/tk8.6/license.terms"))
        found = 0
        for path, original in candidates:
            if not re.match(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)([._-].*)?$", path.name, re.I):
                continue
            if path.suffix.lower() not in {"", ".txt", ".md", ".terms"}:
                continue  # Keep the provided TXT version of Microsoft's RTF notice.
            content = path.read_bytes()
            if b"\0" in content or len(content) > 1_000_000:
                raise ValueError(f"Non-text or oversized notice: {name}/{path.name}")
            filename = re.sub(r"^(license|licence|copying|notice|authors)", lambda m: "LICENSE" if m[0].lower() == "licence" else m[0].upper(), path.name, flags=re.I)
            if path.suffix.lower() == ".terms":
                filename = "NOTICE_" + path.name + ".txt"
            version = re.sub(r"[^A-Za-z0-9_.+-]", "_", record["version"])
            relative = Path(name) / version / str(found + 1) / filename
            notices.append((relative, content, name, record["version"], record["build"], original))
            found += 1
        if not found:
            raise FileNotFoundError(f"No supported text notice: {name}")
    destination.mkdir(parents=True, exist_ok=False)
    rows = []
    for relative, content, name, version, build, original in notices:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        rows.append(f"| {name} | {version} | {build} | `{original}` | `{relative.as_posix()}` | `{hashlib.sha256(content).hexdigest()}` |")
    (destination / "README.md").write_text(
        "# Runtime notice copies\n\n"
        "Original bytes from the exact local runtime package cache/prefix, not rewritten license grants.\n"
        "Selection is explicit and is not a complete runtime SBOM or redistribution clearance.\n"
        "Microsoft's supplied TXT rendering is copied; its duplicate RTF is omitted.\n"
        "No binaries, environment records, credentials, models or research data are copied.\n\n"
        "| Package | Version | Build | Original relative location | Copy | SHA-256 |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return len(notices)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--package", required=True, action="append")
    args = parser.parse_args()
    count = collect(args.prefix, args.output, args.package)
    print(f"Copied {count} original runtime notice texts.")


if __name__ == "__main__":
    main()
