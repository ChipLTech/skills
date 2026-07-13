#!/usr/bin/env bash
set -euo pipefail

# Validate the installed runtime from outside source trees so imports come from
# the installed artifacts instead of editable checkouts.
workdir="${1:-/tmp}"
cd "$workdir"

python3 - <<'PY'
import numpy as np
import torch
print('numpy', np.__version__)
print('torch', torch.__version__)
print('torch_numpy_bridge', torch.tensor([0.1], dtype=torch.float32).numpy())
print('torch_dlc', torch.backends.dlc.is_available() if hasattr(torch.backends, 'dlc') else 'no torch.backends.dlc')
try:
    import vllm
    print('vllm', vllm.__version__)
except Exception as exc:
    print('vllm_import_error', repr(exc))
try:
    import vllm_dlc
    print('vllm_dlc', vllm_dlc.__file__)
except Exception as exc:
    print('vllm_dlc_import_error', repr(exc))
PY

python3 -m pip list | rg '^(vllm|vllm-dlc|vllm_dlc|UNKNOWN|triton|torch|numpy|opencv-python-headless|fastapi)\b' || true
