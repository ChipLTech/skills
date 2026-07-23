#!/usr/bin/env python3
"""Normalize query-only cltech_smi observations for operational regression."""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path


def process_group_members(process_group: int) -> set[int]:
    if process_group <= 0:
        return set()
    try:
        processes = subprocess.run(
            ["/usr/bin/ps", "-eo", "pid=,pgid="],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("failed to inspect process group") from error
    members = set()
    for line in processes.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and all(field.isdigit() for field in fields):
            pid, pgid = map(int, fields)
            if pgid == process_group:
                members.add(pid)
    return members


def device_pids(device_index: int, device_root: Path) -> list[int]:
    device = device_root / f"cltech{device_index}"
    if not device.exists():
        raise RuntimeError(f"missing device node {device}")
    observations = []
    for _ in range(2):
        process = None
        try:
            process = subprocess.Popen(
                ["/usr/bin/lsof", "-t", str(device)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = process.communicate(timeout=10)
        except (OSError, subprocess.TimeoutExpired) as error:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            raise RuntimeError(f"failed to inspect {device}") from error
        if process.returncode not in {0, 1} or stderr.strip():
            raise RuntimeError(f"failed to inspect {device}")
        observed = {
            int(line)
            for line in stdout.splitlines()
            if line.strip().isdigit()
        }
        observed.discard(process.pid)
        observations.append(observed)
    return sorted(observations[0] & observations[1])


def vendor_process_pids(output: str) -> dict[int, set[int]]:
    observed: dict[int, set[int]] = {}
    in_process_table = False
    for line in output.splitlines():
        if "[ Process Information ]" in line:
            in_process_table = True
            continue
        if not in_process_table:
            continue
        match = re.match(r"^\|\s*(\d+)\s+(\d+)\s+", line)
        if match:
            observed.setdefault(int(match.group(1)), set()).add(int(match.group(2)))
    return observed


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--sample-point", required=True)
    parser.add_argument("--server-pid", required=True, type=int)
    parser.add_argument("--process-group", required=True, type=int)
    parser.add_argument("--device-count", required=True, type=int)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--device-root", type=Path, default=Path("/dev"))
    parser.add_argument("--smi-executable", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.sample_point not in {
        "before_launch",
        "after_ready",
        "during_request",
        "after_cleanup",
    }:
        return 10
    process = subprocess.run(
        [str(arguments.smi_executable), "--list-tpus"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if process.returncode != 0:
        return 20
    excluded = subprocess.run(
        [str(arguments.smi_executable), "--list-excluded-tpus"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if excluded.returncode != 0:
        return 20
    capacity = subprocess.run(
        [
            str(arguments.smi_executable),
            "--query-dlc=memory.total",
            "--format=csv,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if capacity.returncode != 0:
        return 20
    status = subprocess.run(
        [str(arguments.smi_executable)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if status.returncode != 0 or "[ Process Information ]" not in status.stdout:
        return 20
    vendor_pids = vendor_process_pids(status.stdout)
    capacities = {}
    for line in capacity.stdout.splitlines():
        match = re.fullmatch(r"TPU\[(\d+)\]\s+(.+)", line.strip())
        if match is None:
            return 20
        try:
            value = float(match.group(2))
        except ValueError:
            return 20
        index = int(match.group(1))
        if index in capacities or not math.isfinite(value) or value <= 0:
            return 20
        capacities[index] = value
    excluded_indices = {
        int(match.group(1))
        for line in excluded.stdout.splitlines()
        if (match := re.match(r"^TPU\s+(\d+):", line.strip()))
    }
    indices = []
    for line in process.stdout.splitlines():
        match = re.match(r"^TPU\s+(\d+):", line.strip())
        if match:
            indices.append(int(match.group(1)))
    if len(indices) < arguments.device_count or len(indices) != len(set(indices)):
        return 20
    if not set(indices).issubset(capacities):
        return 20
    indices = sorted(set(indices) - excluded_indices)
    if len(indices) < arguments.device_count:
        return 20
    try:
        allowed = process_group_members(arguments.process_group)
        observer_members = process_group_members(os.getpgrp())
    except RuntimeError:
        return 20
    if (
        arguments.sample_point != "after_cleanup"
        and arguments.server_pid > 0
        and arguments.process_group > 0
    ):
        if arguments.server_pid not in allowed:
            return 20
    devices = []
    try:
        for index in sorted(indices):
            key = hashlib.sha256(
                f"{arguments.run_id}:cltech-device:{index}".encode("ascii")
            ).hexdigest()
            all_pids = sorted(set(device_pids(index, arguments.device_root)) - observer_members)
            runner_pids = sorted(set(all_pids) & allowed)
            normalized_vendor_pids = sorted(vendor_pids.get(index, set()) & allowed)
            if runner_pids != normalized_vendor_pids:
                return 20
            devices.append(
                {
                    "device_key": f"sha256:{key}",
                    "health": "queryable_not_excluded",
                    "memory_total_mib": capacities[index],
                    "observed_pids": all_pids,
                    "process_pids": runner_pids,
                }
            )
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return 20
    print(
        json.dumps(
            {
                "adapter_schema": "vllm-dlc-smi-observation/v1",
                "devices": devices,
                "sample_point": arguments.sample_point,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
