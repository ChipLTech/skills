#!/usr/bin/env python3
"""Build a deterministic static inventory from an injected vLLM source root."""

import argparse
import ast
import hashlib
import json
from pathlib import Path


METHODS = {
    "all_reduce": "all_reduce",
    "all_gather": "all_gather",
    "all_gather_into_tensor": "all_gather",
    "gather": "gather",
    "reduce_scatter": "reduce_scatter",
    "reduce_scatter_v": "reduce_scatterv",
    "all_gather_v": "all_gatherv",
    "send": "send",
    "recv": "recv",
    "all_to_all": "dispatch",
    "moe_dispatch": "dispatch",
    "moe_combine": "combine",
}


def sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def inventory(
    root: Path,
    pytorch_root: Path | None = None,
    dlc_cl_root: Path | None = None,
    custom_kernel_root: Path | None = None,
) -> dict:
    root = root.resolve(strict=True)
    communicator = root / "vllm/distributed/device_communicators/dlc_communicator.py"
    all2all = root / "vllm/distributed/device_communicators/all2all.py"
    parallel_state = root / "vllm/distributed/parallel_state_dlc.py"
    fused_moe = root / "vllm/model_executor/layers/fused_moe/layer.py"
    moe = root / "vllm/model_executor/layers/fused_moe/flashinfer_cutlass_prepare_finalize.py"
    required = (communicator, all2all, parallel_state, fused_moe, moe)
    if not all(path.is_file() for path in required):
        raise ValueError("blocked_missing_source_inventory_input")
    tree = ast.parse(communicator.read_text(encoding="utf-8"))
    cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DLCCommunicator"
    )
    methods = {
        node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)
    }
    rows = []
    for primitive, method_name in METHODS.items():
        method = methods.get(method_name)
        first = method.body[0] if method and method.body else None
        fail_closed = isinstance(first, ast.Raise) and "blocked_collective_unimplemented" in ast.unparse(first)
        rows.append({
            "primitive": primitive,
            "method": method_name,
            "present": method is not None,
            "fail_closed_unimplemented": fail_closed,
        })
    moe_text = moe.read_text(encoding="utf-8")
    callers = {
        "all_gather_v": ".all_gatherv(" in moe_text,
        "reduce_scatter_v": ".reduce_scatterv(" in moe_text,
        "all_to_all_manager": "all2all_manager" in fused_moe.read_text(encoding="utf-8"),
        "group_coordinator": "device_communicator" in parallel_state.read_text(encoding="utf-8"),
    }
    layer_specs = {
        "pytorch_process_group": (
            pytorch_root,
            "torch/csrc/distributed/c10d/ProcessGroupDLCCL.cpp",
        ),
        "native_dlc_cl": (dlc_cl_root, "src/collectives.cc"),
        "custom_kernel": (custom_kernel_root, "dlc_src/entry_points.cpp"),
    }
    layers = []
    for name, (layer_root, member) in layer_specs.items():
        if layer_root is None:
            layers.append({"layer": name, "status": "blocked", "blocker": "blocked_missing_repository_identity", "snapshot_digest": None})
            continue
        path = layer_root.resolve() / member
        if not path.is_file():
            layers.append({"layer": name, "status": "blocked", "blocker": "blocked_missing_source_inventory_input", "snapshot_digest": None})
            continue
        layers.append({"layer": name, "status": "static_snapshot", "blocker": "blocked_binary_pairing_unresolved", "snapshot_digest": sha256(path.read_bytes())})
    snapshot_payload = b"".join(
        path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0"
        for path in sorted(required)
    )
    result = {
        "schema_version": "vllm-cl-static-collective-inventory/v1",
        "evidence_class": "static_snapshot",
        "acceptance_eligible": False,
        "source_root": str(root),
        "source_snapshot_digest": sha256(snapshot_payload),
        "primitives": rows,
        "moe_callers": callers,
        "layers": layers,
        "claim_boundary": "Claim Boundary: source reachability and fail-closed syntax only; no installed package, binary, model route, or Real DLC Hardware qualification.",
    }
    result["digest"] = sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode())
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vllm-root", type=Path, required=True)
    parser.add_argument("--pytorch-root", type=Path)
    parser.add_argument("--dlc-cl-root", type=Path)
    parser.add_argument("--custom-kernel-root", type=Path)
    args = parser.parse_args()
    try:
        result = inventory(
            args.vllm_root, args.pytorch_root, args.dlc_cl_root,
            args.custom_kernel_root,
        )
    except (OSError, ValueError, SyntaxError) as error:
        print(json.dumps({"status": "blocked", "blocker": str(error)}, sort_keys=True))
        return 20
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
