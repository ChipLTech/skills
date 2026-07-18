#!/usr/bin/env python3
"""Qualify the official cltech_smi environment without starting a model."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


REQUIRED_MOUNTS = (
    "/usr/share/misc/pci.ids",
    "/dev",
    "/sys",
    "/run",
    "/lib/modules",
    "/var/log",
)
OFFICIAL_REMOTE = "git@github.com:ChipLTech/chipltech_smi_lib.git"
OBSERVER = Path(__file__).with_name("observe-cltech-smi.py")


def blocked(reasons: list[str], **identity: object) -> int:
    print(json.dumps({
        "claim_level": "operational_only",
        "model_started": False,
        "reasons": reasons,
        "schema_version": "vllm-dlc-smi-environment-readiness/v1",
        "status": "blocked",
        **identity,
    }, sort_keys=True, separators=(",", ":")))
    return 20


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--smi-executable", required=True, type=Path)
    parser.add_argument("--smi-source-root", required=True, type=Path)
    parser.add_argument("--expected-origin", default=OFFICIAL_REMOTE)
    parser.add_argument("--device-count", required=True, type=int)
    parser.add_argument("--expected-pid-namespace", required=True)
    parser.add_argument("--expected-mount-namespace", required=True)
    parser.add_argument("--mountinfo-path", type=Path, default=Path("/proc/self/mountinfo"))
    parser.add_argument("--status-path", type=Path, default=Path("/proc/self/status"))
    parser.add_argument("--pid1-comm-path", type=Path, default=Path("/proc/1/comm"))
    parser.add_argument("--pid1-cgroup-path", type=Path, default=Path("/proc/1/cgroup"))
    parser.add_argument("--device-root", type=Path, default=Path("/dev"))
    parser.add_argument(
        "--cap-last-cap-path",
        type=Path,
        default=Path("/proc/sys/kernel/cap_last_cap"),
    )
    arguments = parser.parse_args()

    reasons = []
    try:
        mountinfo = arguments.mountinfo_path.read_text()
        mounted = {
            fields[4].replace("\\040", " "): {
                "root": fields[3].replace("\\040", " "),
                "filesystem": fields[separator + 1],
            }
            for line in mountinfo.splitlines()
            if len(fields := line.split()) >= 7
            and (separator := fields.index("-")) + 2 < len(fields)
        }
    except OSError:
        mounted = {}
    resolved_targets = {
        target: str(Path(target).resolve()) for target in REQUIRED_MOUNTS
    }
    for target, resolved in resolved_targets.items():
        if resolved not in mounted:
            reasons.append(f"environment.missing_host_mount:{target}")
    host_mount_shapes = {
        "/usr/share/misc/pci.ids": ({"/usr/share/misc/pci.ids"}, None),
        "/dev": ("/", "devtmpfs"),
        "/sys": ("/", "sysfs"),
        "/run": ({"/", "/run"}, "tmpfs"),
        "/lib/modules": ({"/lib/modules", "/usr/lib/modules"}, None),
        "/var/log": ({"/var/log"}, None),
    }
    for target, (roots, filesystem) in host_mount_shapes.items():
        if isinstance(roots, str):
            roots = {roots}
        observed = mounted.get(resolved_targets[target])
        if observed is not None and (
            observed["root"] not in roots
            or filesystem is not None and observed["filesystem"] != filesystem
        ):
            reasons.append(f"environment.non_host_mount:{target}")

    try:
        status_fields = dict(
            line.split(":", 1) for line in arguments.status_path.read_text().splitlines()
            if ":" in line
        )
        effective = int(status_fields["CapEff"].strip(), 16)
        bounding = int(status_fields["CapBnd"].strip(), 16)
        cap_last_cap = int(arguments.cap_last_cap_path.read_text().strip())
        complete_capabilities = (1 << (cap_last_cap + 1)) - 1
    except (KeyError, OSError, ValueError):
        effective = 0
        bounding = 0
        complete_capabilities = -1
    if effective != complete_capabilities or bounding != complete_capabilities:
        reasons.append("environment.not_privileged")

    try:
        pid1_comm = arguments.pid1_comm_path.read_text().strip()
        pid1_cgroup = arguments.pid1_cgroup_path.read_text().strip().lower()
        pid_namespace = os.readlink("/proc/self/ns/pid")
        mount_namespace = os.readlink("/proc/self/ns/mnt")
    except OSError:
        pid1_comm = ""
        pid1_cgroup = ""
        pid_namespace = ""
        mount_namespace = ""
    if (
        pid1_comm not in {"init", "systemd"}
        or pid_namespace != arguments.expected_pid_namespace
    ):
        reasons.append("environment.host_pid_namespace_unavailable")
    if (
        "/init.scope" not in pid1_cgroup
        or any(marker in pid1_cgroup for marker in ("docker", "containerd", "kubepods", "libpod", "lxc"))
    ):
        reasons.append("environment.host_pid1_scope_unavailable")
    if mount_namespace != arguments.expected_mount_namespace:
        reasons.append("environment.approved_mount_namespace_unavailable")

    executable_digest = None
    if not arguments.smi_executable.is_file() or not arguments.smi_executable.stat().st_mode & 0o111:
        reasons.append("smi.executable_unavailable")
    else:
        executable_digest = "sha256:" + hashlib.sha256(
            arguments.smi_executable.read_bytes()
        ).hexdigest()

    source_sha = None
    git_checks = {
        "sha": ["rev-parse", "HEAD^{commit}"],
        "default_sha": ["rev-parse", "refs/remotes/origin/HEAD^{commit}"],
        "remote": ["remote", "get-url", "origin"],
        "status": ["status", "--porcelain=v1"],
    }
    results = {
        name: subprocess.run(
            ["/usr/bin/git", "-C", str(arguments.smi_source_root), *command],
            check=False,
            capture_output=True,
            text=True,
        )
        for name, command in git_checks.items()
    }
    candidate_sha = results["sha"].stdout.strip()
    if (
        all(result.returncode == 0 for result in results.values())
        and re.fullmatch(r"[0-9a-f]{40}", candidate_sha)
        and results["default_sha"].stdout.strip() == candidate_sha
        and results["remote"].stdout.strip() == arguments.expected_origin
        and not results["status"].stdout.strip()
    ):
        source_sha = candidate_sha
    else:
        reasons.append("smi.source_identity_unavailable")
    remote_head = subprocess.run(
        ["/usr/bin/git", "ls-remote", arguments.expected_origin, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if (
        remote_head.returncode != 0
        or not remote_head.stdout.split()
        or remote_head.stdout.split()[0] != source_sha
    ):
        reasons.append("smi.remote_default_identity_unavailable")
    source_executable = arguments.smi_source_root / "build" / "cltech_smi"
    if executable_digest is not None:
        try:
            source_digest = "sha256:" + hashlib.sha256(
                source_executable.read_bytes()
            ).hexdigest()
        except OSError:
            source_digest = None
        if source_digest != executable_digest:
            reasons.append("smi.executable_source_binding_failed")

    identity = {
        "smi_executable": str(arguments.smi_executable),
        "smi_executable_digest": executable_digest,
        "smi_source_root": str(arguments.smi_source_root),
        "smi_source_sha": source_sha,
    }
    if reasons:
        return blocked(reasons, **identity)

    observation = subprocess.run(
        [
            sys.executable, str(OBSERVER),
            "--sample-point", "before_launch",
            "--server-pid", str(os.getpid()),
            "--process-group", "0",
            "--device-count", str(arguments.device_count),
            "--run-id", "phase10-no-model-qualification",
            "--device-root", str(arguments.device_root),
            "--smi-executable", str(arguments.smi_executable),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if observation.returncode != 0:
        return blocked(["smi.query_qualification_failed"], **identity)

    print(json.dumps({
        "claim_level": "operational_only",
        "model_started": False,
        "qualified_device_count": len(json.loads(observation.stdout)["devices"]),
        "schema_version": "vllm-dlc-smi-environment-readiness/v1",
        "status": "passed",
        **identity,
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
