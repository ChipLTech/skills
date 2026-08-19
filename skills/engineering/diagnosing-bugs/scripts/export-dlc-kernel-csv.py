#!/usr/bin/env python3
"""Export an operator CSV from an existing DLCSynapse launch log."""

import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence


CLOCK_MHZ = 1400
SCHEMA_VERSION = "dlc-kernel-csv-export/v1"


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def load_tool(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("dlc_kernel_log_tool", path)
    if spec is None or spec.loader is None:
        raise ValueError("tool.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if getattr(module, "F", None) != CLOCK_MHZ:
        raise ValueError("tool.py frequency must be 1400 MHz")
    for name in ("get_kernel_launches",):
        if not callable(getattr(module, name, None)):
            raise ValueError("tool.py is missing %s" % name)
    return module


def aggregate(metrics: Sequence[Any]) -> List[Dict[str, Any]]:
    totals: Dict[str, Dict[str, Any]] = {}
    total_cycles = sum(metric.cycles for metric in metrics)
    for metric in metrics:
        row = totals.setdefault(
            metric.name,
            {
                "kernel_name": metric.name,
                "calls": 0,
                "total_cycles": 0,
                "total_ops": 0,
                "total_bytes": 0,
                "total_crt_cycles": 0,
                "max_gflops": 0.0,
                "max_bandwidth_gb_s": 0.0,
            },
        )
        row["calls"] += 1
        row["total_cycles"] += metric.cycles
        row["total_ops"] += metric.ops
        row["total_bytes"] += metric.bytes
        row["total_crt_cycles"] += metric.crt
        row["max_gflops"] = max(
            row["max_gflops"], metric.ops * CLOCK_MHZ / 1000 / metric.cycles
        )
        row["max_bandwidth_gb_s"] = max(
            row["max_bandwidth_gb_s"],
            metric.bytes * CLOCK_MHZ / 1000 / metric.cycles,
        )

    for row in totals.values():
        calls = row["calls"]
        cycles = row["total_cycles"]
        row.update(
            {
                "cycles_pct": cycles * 100 / total_cycles,
                "total_time_us": cycles / CLOCK_MHZ,
                "avg_time_us": cycles / CLOCK_MHZ / calls,
                "avg_crt_us": row["total_crt_cycles"] / CLOCK_MHZ / calls,
                "avg_gflops": row["total_ops"] * CLOCK_MHZ / 1000 / cycles,
                "avg_bandwidth_gb_s": row["total_bytes"]
                * CLOCK_MHZ
                / 1000
                / cycles,
            }
        )
    return sorted(totals.values(), key=lambda row: (-row["total_cycles"], row["kernel_name"]))


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    fields = (
        "kernel_name",
        "calls",
        "total_cycles",
        "cycles_pct",
        "total_time_us",
        "avg_time_us",
        "total_ops",
        "avg_gflops",
        "max_gflops",
        "total_bytes",
        "avg_bandwidth_gb_s",
        "max_bandwidth_gb_s",
        "total_crt_cycles",
        "avg_crt_us",
        "clock_mhz",
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for source in rows:
            row = dict(source)
            row["clock_mhz"] = CLOCK_MHZ
            for field in (
                "cycles_pct",
                "total_time_us",
                "avg_time_us",
                "avg_crt_us",
                "avg_gflops",
                "max_gflops",
                "avg_bandwidth_gb_s",
                "max_bandwidth_gb_s",
            ):
                row[field] = "%.6f" % row[field]
            writer.writerow(row)


def export(log_path: Path, tool_path: Path, output_dir: Path) -> Dict[str, Any]:
    if not log_path.is_file():
        raise ValueError("input log does not exist")
    if not tool_path.is_file():
        raise ValueError("tool.py does not exist")
    output_dir.mkdir(parents=True, exist_ok=True)
    tool = load_tool(tool_path.resolve())
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    metrics = tool.get_kernel_launches(text)
    if not metrics:
        raise ValueError("no DLCSynapse kernel launches were parsed")

    csv_path = output_dir / "operators.csv"
    rows = aggregate(metrics)
    write_csv(csv_path, rows)
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "clock_mhz": CLOCK_MHZ,
        "source_log": {"path": str(log_path.resolve()), "digest": file_digest(log_path)},
        "tool": {"path": str(tool_path.resolve()), "digest": file_digest(tool_path)},
        "operator_csv": {"path": str(csv_path), "digest": file_digest(csv_path)},
        "kernel_count": len(rows),
        "launch_count": len(metrics),
        "claim_boundary": "Diagnostic DLCSynapse launch-log aggregation at 1400 MHz only; not request/rank/device attribution or a formal benchmark.",
    }
    return result


def main(argv: Sequence[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="Existing DLCSynapse .log or .ansi file")
    parser.add_argument(
        "--tool",
        type=Path,
        default=Path("/home/xuansun/llama2-fine-tune/tool.py"),
        help="tool.py used to parse the launch log",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = export(args.log, args.tool, args.output_dir)
    except (OSError, UnicodeDecodeError, ValueError, ZeroDivisionError) as error:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "failed",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
