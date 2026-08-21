#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from manifest_contract import ManifestError, load_manifest, output


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        value, _ = load_manifest(args.manifest.resolve())
    except ManifestError as error:
        print(json.dumps(output("invalid_manifest", [str(error)]), sort_keys=True))
        return 3
    print(json.dumps(output("manifest_valid", case_count=len(value["cases"])), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
