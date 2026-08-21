#!/usr/bin/env python3
"""Classify a path without crossing Host and Docker execution loci."""

import argparse
import json
from pathlib import Path
from typing import Any


def classify_path(
    locus: str,
    path: str,
    *,
    container_available: bool = False,
    mount_source: str | None = None,
) -> dict[str, Any]:
    coordinate = {"execution_locus": locus, "absolute_path": path}
    if not Path(path).is_absolute():
        return {
            "status": "blocked",
            "blocker": "blocked_invalid_path_coordinate",
            "path_coordinate": coordinate,
        }
    if locus == "container" and not container_available:
        return {
            "status": "blocked",
            "blocker": "blocked_missing_container_contract",
            "path_coordinate": coordinate,
            "asset_state": "not_verified",
            "repository_state": "not_verified",
        }
    result: dict[str, Any] = {
        "status": "resolved",
        "blocker": None,
        "path_coordinate": coordinate,
    }
    if mount_source is not None:
        if locus != "container" or not Path(mount_source).is_absolute():
            return {
                "status": "blocked",
                "blocker": "blocked_invalid_mount_mapping",
                "path_coordinate": coordinate,
            }
        result["mount_mapping"] = {
            "host_source": mount_source,
            "container_destination": path,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locus", choices=("host", "container"), required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--container-available", action="store_true")
    parser.add_argument("--mount-source")
    args = parser.parse_args()
    result = classify_path(
        args.locus,
        args.path,
        container_available=args.container_available,
        mount_source=args.mount_source,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "resolved" else 10


if __name__ == "__main__":
    raise SystemExit(main())
