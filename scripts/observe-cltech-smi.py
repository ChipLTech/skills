#!/usr/bin/env python3
"""Compatibility entrypoint for the hardware-observability skill adapter."""

from pathlib import Path


_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "engineering"
    / "dlc-hardware-observability"
    / "scripts"
    / "observe-cltech-smi.py"
)
exec(compile(_SOURCE.read_bytes(), str(_SOURCE), "exec"), globals(), globals())
