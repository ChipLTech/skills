#!/usr/bin/env python3
"""Read-only, injectable Git repository guard for qualification consumers."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _git(root: Path, *arguments: str, binary: bool = False) -> Any:
    return subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=not binary,
    ).stdout


def repository_snapshot(root: Path) -> dict[str, Any]:
    requested = root.absolute()
    try:
        canonical = root.resolve(strict=True)
        top_level = Path(_git(canonical, "rev-parse", "--show-toplevel").strip()).resolve()
    except (OSError, subprocess.CalledProcessError):
        return {
            "status": "not_verified",
            "blocker": "blocked_missing_repository",
            "requested_root": str(requested),
        }
    if canonical != top_level:
        return {
            "status": "blocked",
            "blocker": "blocked_non_authoritative_repository_root",
            "requested_root": str(requested),
            "canonical_root": str(canonical),
            "git_top_level": str(top_level),
        }
    status = _git(top_level, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)
    tracked_diff = _git(top_level, "diff", "--binary", "HEAD", binary=True)
    untracked_names = _git(
        top_level, "ls-files", "--others", "--exclude-standard", "-z", binary=True
    ).split(b"\0")
    untracked_payload = b""
    for raw_name in sorted(name for name in untracked_names if name):
        path = top_level / raw_name.decode("utf-8", errors="surrogateescape")
        if path.is_symlink():
            content = b"symlink\0" + os.fsencode(os.readlink(path))
        else:
            content = b"file\0" + path.read_bytes()
        untracked_payload += raw_name + b"\0" + content + b"\0"
    working_tree_identity = status + b"\0" + tracked_diff + b"\0" + untracked_payload
    return {
        "status": "passed",
        "blocker": None,
        "requested_root": str(requested),
        "canonical_root": str(canonical),
        "git_top_level": str(top_level),
        "head": _git(top_level, "rev-parse", "HEAD^{commit}").strip(),
        "branch": _git(top_level, "branch", "--show-current").strip() or None,
        "dirty": bool(status),
        "status_digest": "sha256:" + hashlib.sha256(working_tree_identity).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    result = repository_snapshot(args.root)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "passed" else 10


if __name__ == "__main__":
    raise SystemExit(main())
