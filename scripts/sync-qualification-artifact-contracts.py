#!/usr/bin/env python3
"""Generate or verify bundled Qualification Artifact contract copies."""

import argparse
import hashlib
import shutil
import sys
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
CONSUMERS = ("diagnosing-bugs", "model-adaptation")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    canonical = (
        root / "skills/engineering/chipltech-context/contracts/qualification-artifact-envelope-v1.schema.json",
        root / "skills/engineering/chipltech-context/contracts/vllm-dlc-collective-selection-v1.schema.json",
        root / "skills/engineering/chipltech-context/scripts/qualification_artifact.py",
    )
    drift = []
    for consumer in CONSUMERS:
        destination = root / f"skills/engineering/{consumer}/scripts/_generated_contracts"
        for source in canonical:
            target = destination / source.name
            if arguments.check:
                if not target.is_file() or digest(source) != digest(target):
                    drift.append(target.relative_to(root).as_posix())
            else:
                destination.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    if drift:
        print("generated contract drift: " + ", ".join(sorted(drift)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
