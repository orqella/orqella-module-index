#!/usr/bin/env python3
"""Validate the Orqella module index.

This intentionally has no third-party dependencies. It checks the schema
shape, platform names, URLs, digests, and duplicate IDs/versions. When the
optional `jsonschema` package is installed, it also validates against
`index.schema.json`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
COMMIT = re.compile(r"^[0-9a-fA-F]{40,64}$")
MODULE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
PLATFORM = re.compile(r"^(linux|macos|windows)-[A-Za-z0-9_]+$")
URL = re.compile(r"^(https://|http://(127\.0\.0\.1|localhost)([:/]|$))")
API_VERSION = "1"


class Invalid(Exception):
    pass


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def check_platforms(values: object, where: str) -> None:
    if values is None:
        return
    expect(isinstance(values, list), f"{where} must be an array")
    seen: set[str] = set()
    for value in values:
        expect(isinstance(value, str), f"{where} entries must be strings")
        expect(bool(PLATFORM.match(value)), f"{where} has invalid platform {value!r}")
        expect(value not in seen, f"{where} repeats platform {value!r}")
        seen.add(value)


def check_url(value: object, where: str) -> None:
    expect(isinstance(value, str), f"{where} must be a string")
    expect(bool(URL.match(value)), f"{where} must use HTTPS (or loopback HTTP): {value!r}")


def check_module(module: object) -> tuple[str, list[str]]:
    expect(isinstance(module, dict), "module entries must be objects")
    module_id = module.get("id")
    expect(isinstance(module_id, str), "module.id is required")
    expect(bool(MODULE_ID.match(module_id)), f"invalid module id {module_id!r}")
    expect(isinstance(module.get("name"), str) and module["name"].strip(), f"{module_id}: name is required")
    publisher = module.get("publisher")
    expect(isinstance(publisher, dict), f"{module_id}: publisher is required")
    expect(isinstance(publisher.get("name"), str) and publisher["name"].strip(), f"{module_id}: publisher.name is required")
    if publisher.get("url"):
        check_url(publisher["url"], f"{module_id}: publisher.url")
    if module.get("homepage"):
        check_url(module["homepage"], f"{module_id}: homepage")
    expect(module.get("node_scope", "node") in {"node", "aggregate", "hub"}, f"{module_id}: invalid node_scope")
    check_platforms(module.get("platforms"), f"{module_id}: platforms")
    for field in ("tags", "permissions"):
        if field in module:
            expect(isinstance(module[field], list), f"{module_id}: {field} must be an array")
            for value in module[field]:
                expect(isinstance(value, str), f"{module_id}: {field} entries must be strings")
    versions = module.get("versions")
    expect(isinstance(versions, list) and versions, f"{module_id}: versions must not be empty")
    seen_versions: set[str] = set()
    for version in versions:
        expect(isinstance(version, dict), f"{module_id}: version entries must be objects")
        value = version.get("version")
        expect(isinstance(value, str) and value.strip(), f"{module_id}: version is required")
        expect(value not in seen_versions, f"{module_id}: duplicate version {value}")
        seen_versions.add(value)
        expect(version.get("api_version", API_VERSION) == API_VERSION, f"{module_id} {value}: unsupported api_version")
        if version.get("notes_url"):
            check_url(version["notes_url"], f"{module_id} {value}: notes_url")
        distributions = version.get("distributions")
        expect(isinstance(distributions, list) and distributions, f"{module_id} {value}: distributions must not be empty")
        for distribution in distributions:
            check_distribution(module_id, value, distribution)
    return module_id, list(seen_versions)


def check_distribution(module_id: str, version: str, distribution: object) -> None:
    where = f"{module_id} {version}"
    expect(isinstance(distribution, dict), f"{where}: distribution must be an object")
    check_platforms(distribution.get("platforms"), f"{where}: platforms")
    digest = distribution.get("tree_sha256")
    expect(isinstance(digest, str) and bool(SHA256.match(digest)), f"{where}: invalid tree_sha256")
    backend = distribution.get("backend")
    if backend is not None:
        expect(isinstance(backend, dict), f"{where}: backend must be an object")
        expect(backend.get("kind", "none") in {"none", "sidecar"}, f"{where}: invalid backend kind")
        check_platforms(backend.get("platforms"), f"{where}: backend.platforms")
    source = distribution.get("source")
    expect(isinstance(source, dict), f"{where}: source is required")
    kind = source.get("type")
    if kind == "git":
        check_url(source.get("url"), f"{where}: git url")
        commit = source.get("commit")
        expect(isinstance(commit, str) and bool(COMMIT.match(commit)), f"{where}: invalid git commit")
        if source.get("ref") is not None:
            expect(isinstance(source["ref"], str), f"{where}: git ref must be a string")
    elif kind == "archive":
        check_url(source.get("url"), f"{where}: archive url")
        expect(source.get("format") in {"zip", "tar.gz"}, f"{where}: archive format must be zip or tar.gz")
        checksum = source.get("sha256")
        expect(isinstance(checksum, str) and bool(SHA256.match(checksum)), f"{where}: invalid archive sha256")
        if source.get("size") is not None:
            expect(isinstance(source["size"], int) and source["size"] > 0, f"{where}: invalid archive size")
    else:
        raise Invalid(f"{where}: source.type must be git or archive")


def validate(index: object, schema_path: Path | None = None) -> tuple[int, int]:
    expect(isinstance(index, dict), "index.json must contain an object")
    expect(index.get("schema") == 1, "unsupported schema version")
    if index.get("updated_at") is not None:
        expect(isinstance(index["updated_at"], str), "updated_at must be a string")
    modules = index.get("modules")
    expect(isinstance(modules, list), "modules must be an array")
    seen_ids: set[str] = set()
    version_count = 0
    for module in modules:
        module_id, versions = check_module(module)
        expect(module_id not in seen_ids, f"duplicate module id {module_id}")
        seen_ids.add(module_id)
        version_count += len(versions)

    if schema_path and schema_path.is_file():
        try:
            import jsonschema  # type: ignore
        except ImportError:
            jsonschema = None
        if jsonschema:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(index, schema)
    return len(modules), version_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=Path(__file__).resolve().parents[1] / "index.json")
    parser.add_argument("--schema", type=Path, default=Path(__file__).resolve().parents[1] / "index.schema.json")
    args = parser.parse_args(argv)
    try:
        index = json.loads(args.index.read_text(encoding="utf-8"))
        modules, versions = validate(index, args.schema)
    except (OSError, json.JSONDecodeError, Invalid) as error:
        print(f"invalid module index: {error}", file=sys.stderr)
        return 1
    print(f"valid module index: {modules} modules, {versions} versions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
