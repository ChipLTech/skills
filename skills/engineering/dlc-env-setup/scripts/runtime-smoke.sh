#!/usr/bin/env bash
set -euo pipefail

# Validate installed packages from outside source trees. Real hardware model
# validation must additionally opt in to the layered device execution gate.
workdir="/tmp"
workdir_set=0
require_device_execution=0
require_vllm=0
require_vllm_dlc=0
skip_vllm_dlc=0
device_index=0

usage() {
  cat <<'EOF'
Usage: runtime-smoke.sh [workdir] [options]

Options:
  --require-device-execution  Run allocation/H2D/device-op/sync/D2H correctness
  --device-index N            Logical DLC device index for execution (default: 0)
  --require-vllm              Fail if vllm cannot be imported
  --require-vllm-dlc          Fail if vllm_dlc cannot be imported
  --skip-vllm-dlc             Do not import vllm_dlc for built-in platform use
  -h, --help                  Show this help

Set DLC_PACKAGE_SMOKE_TIMEOUT to override the 45-second package timeout.
Set DLC_RUNTIME_SMOKE_TIMEOUT to override the 45-second execution timeout.
Use DLC_VISIBLE_DEVICES outside this script to define the physical device map.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-device-execution)
      require_device_execution=1
      shift
      ;;
    --device-index)
      if [[ $# -lt 2 ]]; then
        printf '%s\n' '--device-index requires a value' >&2
        exit 2
      fi
      device_index="$2"
      shift 2
      ;;
    --require-vllm)
      require_vllm=1
      shift
      ;;
    --require-vllm-dlc)
      require_vllm_dlc=1
      shift
      ;;
    --skip-vllm-dlc)
      skip_vllm_dlc=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ "$workdir_set" == "1" ]]; then
        printf 'Unexpected positional argument: %s\n' "$1" >&2
        exit 2
      fi
      workdir="$1"
      workdir_set=1
      shift
      ;;
  esac
done

if [[ ! "$device_index" =~ ^[0-9]+$ ]]; then
  printf '%s\n' '--device-index must be a non-negative integer' >&2
  exit 2
fi

if [[ "$require_vllm_dlc" == "1" && "$skip_vllm_dlc" == "1" ]]; then
  printf '%s\n' '--require-vllm-dlc and --skip-vllm-dlc are mutually exclusive' >&2
  exit 2
fi

package_timeout_seconds="${DLC_PACKAGE_SMOKE_TIMEOUT:-45}"
if [[ ! "$package_timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
  printf '%s\n' 'DLC_PACKAGE_SMOKE_TIMEOUT must be a positive integer' >&2
  exit 2
fi

if [[ ! -d "$workdir" ]]; then
  printf 'Workdir does not exist: %s\n' "$workdir" >&2
  exit 2
fi

cd "$workdir"

printf 'package_smoke_timeout_seconds %s\n' "$package_timeout_seconds"

REQUIRE_VLLM="$require_vllm" \
  REQUIRE_VLLM_DLC="$require_vllm_dlc" \
  SKIP_VLLM_DLC="$skip_vllm_dlc" \
  timeout --signal=TERM --kill-after=5 "$package_timeout_seconds" python3 - <<'PY'
import os
from importlib import metadata

import numpy as np
import torch

print('numpy', np.__version__)
print('torch', torch.__version__)
print('torch_numpy_bridge', torch.tensor([0.1], dtype=torch.float32).numpy())
dlc_available = hasattr(torch.backends, 'dlc') and torch.backends.dlc.is_available()
print('torch_dlc', dlc_available)
if not dlc_available:
    raise RuntimeError('DLC Platform backend is unavailable')
try:
    import vllm
    print('vllm', vllm.__version__)
    print('vllm_metadata', metadata.version('vllm'))
except Exception as exc:
    print('vllm_import_error', repr(exc))
    if os.environ['REQUIRE_VLLM'] == '1':
        raise
if os.environ['SKIP_VLLM_DLC'] == '1':
    print('vllm_dlc', 'not_applicable_by_contract')
else:
    try:
        import vllm_dlc
        print('vllm_dlc', vllm_dlc.__file__)
        print('vllm_dlc_metadata', metadata.version('vllm-dlc'))
    except Exception as exc:
        print('vllm_dlc_import_error', repr(exc))
        if os.environ['REQUIRE_VLLM_DLC'] == '1':
            raise
PY

if [[ "$require_device_execution" == "1" ]]; then
  timeout_seconds="${DLC_RUNTIME_SMOKE_TIMEOUT:-45}"
  if [[ ! "$timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
    printf '%s\n' 'DLC_RUNTIME_SMOKE_TIMEOUT must be a positive integer' >&2
    exit 2
  fi

  printf 'runtime_execution_timeout_seconds %s\n' "$timeout_seconds"
  printf 'runtime_execution_device_index %s\n' "$device_index"

  DLC_RUNTIME_SMOKE_DEVICE_INDEX="$device_index" \
    timeout --signal=TERM --kill-after=5 "$timeout_seconds" python3 - <<'PY'
import os

import torch


def report(name, operation):
    print(f"BEGIN {name}", flush=True)
    value = operation()
    print(f"PASS {name}", flush=True)
    return value


device_index = int(os.environ["DLC_RUNTIME_SMOKE_DEVICE_INDEX"])
device_name = f"dlc:{device_index}"
print(f"torch={torch.__version__} path={torch.__file__}", flush=True)

print("BEGIN backend_availability", flush=True)
backend_available = (
    hasattr(torch, "dlc")
    and hasattr(torch.backends, "dlc")
    and torch.backends.dlc.is_available()
)
if not backend_available:
    raise RuntimeError("DLC Platform backend/API surface is unavailable")
print("PASS backend_availability", flush=True)

device_count = report("device_count", torch.dlc.device_count)
if device_count <= device_index:
    raise RuntimeError(
        f"logical device index {device_index} is unavailable; "
        f"device_count={device_count}"
    )

report("device_properties", lambda: torch.dlc.get_device_properties(device_index))
report("set_device", lambda: torch.dlc.set_device(device_index))
report("mem_get_info", torch.dlc.mem_get_info)

allocated = report("allocation_submit", lambda: torch.empty(1, device=device_name))
print(
    f"META allocation shape={tuple(allocated.shape)} "
    f"dtype={allocated.dtype} device={allocated.device}",
    flush=True,
)

host = report("host_source", lambda: torch.ones(1, dtype=torch.float32))
device = report("h2d_submit", lambda: host.to(device_name))
print(
    f"META h2d shape={tuple(device.shape)} "
    f"dtype={device.dtype} device={device.device}",
    flush=True,
)

result = report("device_op_submit", lambda: device + 1)
print(
    f"META device_op shape={tuple(result.shape)} "
    f"dtype={result.dtype} device={result.device}",
    flush=True,
)
report("device_op_completion_synchronize", torch.dlc.synchronize)

copied = report("d2h", result.cpu)
if copied.item() != 2:
    raise AssertionError(
        f"device correctness mismatch: expected 2, got {copied.item()}"
    )
print("LAYERED_RUNTIME_EXECUTION_PASS", flush=True)
PY
fi
