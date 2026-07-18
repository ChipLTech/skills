#!/usr/bin/env python3
"""Own one typed local vLLM server lifecycle for operational regression."""

import argparse
import importlib.util
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def listener_owned_by_process_group(port: int) -> bool:
    try:
        listeners = subprocess.run(
            ["/usr/bin/lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if listeners.returncode != 0:
        return False
    process_group = os.getpgrp()
    pids = [int(line) for line in listeners.stdout.splitlines() if line.isdigit()]
    if not pids:
        return False
    try:
        return all(os.getpgid(pid) == process_group for pid in pids)
    except ProcessLookupError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--ready-file", required=True, type=Path)
    parser.add_argument("--host", choices=("127.0.0.1",), default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tokenizer", required=True)
    parser.add_argument("--served-model-name", required=True)
    parser.add_argument("--tensor-parallel-size", required=True, type=int)
    parser.add_argument("--pipeline-parallel-size", required=True, type=int)
    parser.add_argument("--dtype", required=True)
    parser.add_argument("--quantization", required=True)
    parser.add_argument("--max-model-len", required=True, type=int)
    parser.add_argument("--max-num-batched-tokens", required=True, type=int)
    parser.add_argument("--enforce-eager", action="store_true", required=True)
    parser.add_argument("--expected-vllm-root", required=True, type=Path)
    parser.add_argument("--expected-vllm-dlc-root", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.ready_file.exists() or arguments.ready_file.is_symlink():
        return 10
    for module, root in {
        "vllm.entrypoints.cli.main": arguments.expected_vllm_root.resolve(),
        "vllm._C": arguments.expected_vllm_root.resolve(),
        "vllm_dlc": arguments.expected_vllm_dlc_root.resolve(),
        "vllm_dlc.vllm_dlc_C": arguments.expected_vllm_dlc_root.resolve(),
    }.items():
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None:
            return 20
        try:
            Path(spec.origin).resolve().relative_to(root)
        except ValueError:
            return 20
    command = [
        sys.executable,
        "-m",
        "vllm.entrypoints.cli.main",
        "serve",
        arguments.model,
        "--host",
        arguments.host,
        "--port",
        str(arguments.port),
        "--tokenizer",
        arguments.tokenizer,
        "--served-model-name",
        arguments.served_model_name,
        "--tensor-parallel-size",
        str(arguments.tensor_parallel_size),
        "--pipeline-parallel-size",
        str(arguments.pipeline_parallel_size),
        "--dtype",
        arguments.dtype,
        "--max-model-len",
        str(arguments.max_model_len),
        "--max-num-batched-tokens",
        str(arguments.max_num_batched_tokens),
        "--enforce-eager",
    ]
    if arguments.quantization != "none":
        command.extend(["--quantization", arguments.quantization])
    child_environment = {
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for name in ("DLC_VISIBLE_DEVICES", "DLC_SYN_COPY_ASYNC"):
        if name in os.environ:
            child_environment[name] = os.environ[name]
    child = subprocess.Popen(command, env=child_environment)

    def forward(signum, _frame):
        if child.poll() is None:
            child.send_signal(signum)

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if child.poll() is not None:
            return child.returncode
        with socket.socket() as connection:
            connection.settimeout(0.2)
            if (
                connection.connect_ex((arguments.host, arguments.port)) == 0
                and listener_owned_by_process_group(arguments.port)
            ):
                temporary = arguments.ready_file.with_suffix(".tmp")
                temporary.write_text(str(arguments.port), encoding="ascii")
                temporary.replace(arguments.ready_file)
                return child.wait()
        time.sleep(0.1)
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
    return 30


if __name__ == "__main__":
    raise SystemExit(main())
