#!/usr/bin/env python3
"""Compatibility entrypoint for the hardware-observability qualifier."""

from pathlib import Path


_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "engineering"
    / "dlc-hardware-observability"
    / "scripts"
    / "qualify-vllm-dlc-smi-environment.py"
)
exec(compile(_SOURCE.read_bytes(), str(_SOURCE), "exec"), globals(), globals())
