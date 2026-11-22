#!/usr/bin/env python3
"""Compute the Orqella module tree digest used by the module index and signing.

The algorithm matches `src/modules/signing.rs::digest_tree`:

* files are sorted by relative UTF-8 path;
* each entry hashes its path length and bytes;
* regular files hash an executable flag, length, and contents;
* symlinks hash their target instead of following it;
* runtime paths (`.git`, `data/`, caches, virtualenvs, signatures) are excluded.

Examples:
    python3 scripts/tree_digest.py --path ../modules/system --ref main
    python3 scripts/tree_digest.py --repo https://github.com/orqella/orqella-system --ref main
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

EXCLUDES = {
    ".git",
    ".config",
    ".cache",
    ".local",
    "target",
    "node_modules",
    ".venv",
    "__pycache__",
    "sidecar.log",
    "ORQELLA_SIGNATURE.json",
}


def tree_digest(root: Path) -> str:
    files: list[tuple[str, Path]] = []

    def walk(directory: Path) -> None:
        for entry in os.scandir(directory):
            name = entry.name
            if name in EXCLUDES:
                continue
            if directory == root and name.lower() == "data":
                continue
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if entry.is_symlink():
                files.append((relative, path))
            elif entry.is_dir(follow_symlinks=False):
                walk(path)
            elif entry.is_file(follow_symlinks=False):
                files.append((relative, path))

    walk(root)
    files.sort(key=lambda item: item[0].encode("utf-8"))
    digest = hashlib.sha256()
    for relative, path in files:
        relative_bytes = relative.encode("utf-8")
        digest.update(len(relative_bytes).to_bytes(8, "little"))
        digest.update(relative_bytes)
        if path.is_symlink():
            target = os.readlink(path).encode("utf-8")
            digest.update(b"L")
            digest.update(len(target).to_bytes(8, "little"))
            digest.update(target)
            continue
        data = path.read_bytes()
        digest.update(b"F")
        digest.update(b"\x01" if os.stat(path).st_mode & 0o111 else b"\x00")
        digest.update(len(data).to_bytes(8, "little"))
        digest.update(data)
    return digest.hexdigest()


def checkout_repo(repo: str, ref: str | None, destination: Path) -> Path:
    subprocess.run(["git", "clone", "--quiet", repo, str(destination)], check=True)
    if ref:
        subprocess.run(
            ["git", "-C", str(destination), "checkout", "--quiet", "--detach", ref],
            check=True,
        )
    return destination


def archive_ref(path: Path, ref: str, destination: Path) -> Path:
    archive = destination / "tree.tar"
    with archive.open("wb") as output:
        subprocess.run(
            ["git", "-C", str(path), "archive", "--format=tar", ref],
            check=True,
            stdout=output,
        )
    tree = destination / "tree"
    tree.mkdir()
    with tarfile.open(archive) as tar:
        try:
            tar.extractall(tree, filter="data")
        except TypeError:  # Python < 3.12
            tar.extractall(tree)
    return tree


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--path", type=Path, help="local checkout")
    source.add_argument("--repo", help="git repository URL to clone")
    parser.add_argument("--ref", help="branch, tag, or commit to read")
    parser.add_argument("--expected", help="fail when the digest does not match")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="orqella-tree-digest.") as temporary:
        temp = Path(temporary)
        if args.repo:
            root = checkout_repo(args.repo, args.ref, temp / "repo")
        else:
            root = args.path.resolve()
            if not root.joinpath("module.toml").is_file():
                parser.error(f"no module.toml under {root}")
            if args.ref:
                root = archive_ref(root, args.ref, temp)
        digest = tree_digest(root)
    print(digest)
    if args.expected and digest.lower() != args.expected.lower():
        print(f"expected: {args.expected}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
