#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path


CRT_FILES = (
    "dlc_crt.hex",
    "dlc_crt_xys1.hex",
    "dlc_crt_cmem.hex",
    "dlc_crt_cmem_xys1.hex",
)
TARGET_MARKERS = {"dlc": "0DLC", "tyd": "0TYD", "hhp": "0HHP"}
POLICY_SCHEMA = "io.chipltech.stack-compatibility-policy/v1"
RESULT_SCHEMA = "io.chipltech.stack-preflight-result/v1"
POLICY_KEYS = {
    "profile_id",
    "status",
    "target",
    "marker_hex",
    "driver_api",
    "runtime_api",
    "crt",
    "kernel_library_sha256",
    "llvm_sha",
    "qualification_evidence",
    "image_ids",
}
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class UsageError(Exception):
    pass


class BundleIncompleteError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def emit(reason_code, exit_code, **fields):
    print(
        json.dumps(
            {
                "schema": RESULT_SCHEMA,
                "result": "compatible" if exit_code == 0 else "incompatible",
                "reason_code": reason_code,
                "exit_code": exit_code,
                **fields,
            },
            sort_keys=True,
        )
    )
    return exit_code


def read_regular_file(path, dir_fd=None):
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, dir_fd=dir_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError(f"not a regular file: {path}")
        digest = hashlib.sha256()
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise OSError(f"file changed during inspection: {path}")
        data = b"".join(chunks)
        return data, hashlib.sha256(data).hexdigest()
    finally:
        os.close(fd)


def read_policy_bytes(path):
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise OSError(f"not a regular file: {path}")
        chunks = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise OSError(f"file changed during inspection: {path}")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _extra_keys(obj, allowed):
    return set(obj) - allowed


def validate_profile(profile):
    if not isinstance(profile, dict):
        return False
    if _extra_keys(profile, POLICY_KEYS):
        return False
    profile_id = profile.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        return False
    status = profile.get("status")
    if status not in ("approved", "revoked"):
        return False
    target = profile.get("target")
    if target not in TARGET_MARKERS:
        return False
    marker_hex = profile.get("marker_hex")
    if not re.fullmatch(r"[0-9a-f]{8}", marker_hex or ""):
        return False
    if status == "approved" and marker_hex != TARGET_MARKERS[target].encode().hex():
        return False
    driver_api = profile.get("driver_api")
    runtime_api = profile.get("runtime_api")
    if type(driver_api) is not int or type(runtime_api) is not int:
        return False
    if driver_api <= 0 or runtime_api <= 0:
        return False
    crt = profile.get("crt")
    if not isinstance(crt, dict) or set(crt) != set(CRT_FILES):
        return False
    for artifact in crt.values():
        if not isinstance(artifact, dict):
            return False
        if not re.fullmatch(r"[0-9a-f]{64}", artifact.get("sha256", "")):
            return False
        if type(artifact.get("size")) is not int or artifact["size"] <= 4:
            return False
    if not re.fullmatch(r"[0-9a-f]{64}", profile.get("kernel_library_sha256", "")):
        return False
    if not re.fullmatch(r"[0-9a-f]{40}", profile.get("llvm_sha", "")):
        return False
    evidence = profile.get("qualification_evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        return False
    image_ids = profile.get("image_ids")
    if image_ids is None:
        image_ids = []
    if not isinstance(image_ids, list):
        return False
    if status == "approved" and not image_ids:
        return False
    if any(not IMAGE_ID_RE.fullmatch(item) for item in image_ids):
        return False
    return True


def validate_policy(policy):
    if not isinstance(policy, dict):
        return False
    if _extra_keys(policy, {"schema", "profiles"}):
        return False
    if policy.get("schema") != POLICY_SCHEMA:
        return False
    profiles = policy.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        return False
    profile_ids = set()
    identities = set()
    for profile in profiles:
        if not validate_profile(profile):
            return False
        profile_id = profile["profile_id"]
        if profile_id in profile_ids:
            return False
        profile_ids.add(profile_id)
        identity = _profile_identity(profile)
        if identity in identities:
            return False
        identities.add(identity)
    return True


def _profile_identity(profile):
    return (
        profile["target"],
        profile["marker_hex"],
        profile["driver_api"],
        profile["runtime_api"],
        json.dumps(profile["crt"], sort_keys=True),
        profile["kernel_library_sha256"],
        profile["llvm_sha"],
    )


def _observed_identity(args, crt, marker_hex, kernel_sha):
    return (
        args.target,
        marker_hex,
        args.driver_api,
        args.runtime_api,
        json.dumps(crt, sort_keys=True),
        kernel_sha,
        args.llvm_sha,
    )


def _inspect_artifacts(crt_dir, kernel_library):
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    dir_fd = os.open(crt_dir, flags)
    try:
        if not stat.S_ISDIR(os.fstat(dir_fd).st_mode):
            raise OSError(f"not a directory: {crt_dir}")
        with os.scandir(dir_fd) as iterator:
            names = {
                entry.name
                for entry in iterator
                if entry.is_file(follow_symlinks=False) and entry.name.startswith("dlc_crt")
            }
        if names != set(CRT_FILES):
            raise BundleIncompleteError(f"CRT bundle incomplete: {sorted(names)}")
        crt = {}
        markers = set()
        for name in CRT_FILES:
            data, sha256 = read_regular_file(name, dir_fd=dir_fd)
            markers.add(data[:4].hex())
            crt[name] = {"sha256": sha256, "size": len(data)}
    finally:
        os.close(dir_fd)
    _, kernel_sha = read_regular_file(kernel_library)
    return crt, markers, kernel_sha


def main():
    parser = _Parser(prog="stack-preflight.py")
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--target", choices=tuple(TARGET_MARKERS), required=True)
    parser.add_argument("--driver-api", type=int, required=True)
    parser.add_argument("--runtime-api", type=int, required=True)
    parser.add_argument("--crt-dir", type=Path, required=True)
    parser.add_argument("--kernel-library", type=Path, required=True)
    parser.add_argument("--llvm-sha", required=True)
    try:
        args = parser.parse_args()
    except UsageError as error:
        return emit("invalid_arguments", 2, detail=str(error))

    if not IMAGE_ID_RE.fullmatch(args.image_id):
        return emit("identity_unavailable", 11, component="immutable image")
    if args.driver_api <= 0 or args.runtime_api <= 0:
        return emit("identity_unavailable", 11, component="Driver/Runtime API")
    if args.driver_api != args.runtime_api:
        return emit(
            "driver_runtime_api_mismatch",
            2,
            driver_api=args.driver_api,
            runtime_api=args.runtime_api,
        )
    if not re.fullmatch(r"[0-9a-f]{40}", args.llvm_sha):
        return emit("identity_unavailable", 11, component="LLVM")

    try:
        policy_bytes = read_policy_bytes(args.policy)
        policy = json.loads(policy_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return emit("policy_unavailable", 10, detail=str(error))

    try:
        if not validate_policy(policy):
            return emit("invalid_policy", 10)
        crt, markers, kernel_sha = _inspect_artifacts(args.crt_dir, args.kernel_library)
    except BundleIncompleteError as error:
        return emit("crt_bundle_incomplete", 3, detail=str(error))
    except OSError as error:
        return emit("identity_unavailable", 11, detail=str(error))
    except Exception as error:
        return emit("invalid_policy", 10, detail=str(error))

    if len(markers) != 1:
        return emit("crt_bundle_inconsistent", 4, marker_hex=sorted(markers), target=args.target)
    marker_hex = next(iter(markers))
    identity = _observed_identity(args, crt, marker_hex, kernel_sha)

    revoked_match = None
    for profile in policy["profiles"]:
        if profile["status"] != "revoked":
            continue
        if _profile_identity(profile) != identity:
            continue
        image_ids = profile.get("image_ids") or []
        if image_ids and args.image_id not in image_ids:
            continue
        revoked_match = profile
        break
    if revoked_match is not None:
        return emit(
            "known_bad_profile",
            5,
            profile_id=revoked_match["profile_id"],
            image_id=args.image_id,
            qualification_evidence=revoked_match["qualification_evidence"],
            identity=identity,
        )

    approved_match = None
    for profile in policy["profiles"]:
        if profile["status"] != "approved":
            continue
        if _profile_identity(profile) != identity:
            continue
        image_ids = profile.get("image_ids") or []
        if args.image_id not in image_ids:
            continue
        approved_match = profile
        break
    if approved_match is not None:
        return emit(
            "approved_profile",
            0,
            profile_id=approved_match["profile_id"],
            image_id=args.image_id,
            qualification_evidence=approved_match["qualification_evidence"],
            identity=identity,
        )

    if marker_hex != TARGET_MARKERS[args.target].encode().hex():
        return emit(
            "crt_bundle_inconsistent",
            4,
            marker_hex=marker_hex,
            target=args.target,
        )
    return emit("unknown_profile", 6, image_id=args.image_id, identity=identity)


if __name__ == "__main__":
    sys.exit(main())
