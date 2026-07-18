#!/usr/bin/env python3
"""Build and prove a tokenizer-derived long prefix from local assets only."""

import argparse
import hashlib
import json
from pathlib import Path


NON_MONOTONIC_SCAN_LIMIT = 64


def sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def build_long_prefix(encode, threshold: int, maximum: int) -> tuple[str, list[int]]:
    if threshold < 0 or maximum <= threshold:
        raise ValueError("invalid token bounds")

    unit_limit = maximum * 8
    units = []
    encodings = {}

    def encode_units(length):
        while len(units) < length:
            units.append(f"operational-{len(units)}")
        if length not in encodings:
            prompt = " ".join(units[:length])
            encodings[length] = (prompt, encode(prompt))
        return encodings[length]

    lower = 0
    upper = 1
    encode_units(lower)
    while len(encode_units(upper)[1]) <= threshold:
        lower = upper
        if upper == unit_limit:
            raise ValueError("token threshold not reached")
        upper = min(upper * 2, unit_limit)

    while lower + 1 < upper:
        middle = (lower + upper) // 2
        if len(encode_units(middle)[1]) > threshold:
            upper = middle
        else:
            lower = middle

    candidate = upper
    scan_start = max(0, candidate - NON_MONOTONIC_SCAN_LIMIT)
    scan_counts = [
        len(encode_units(length)[1])
        for length in range(scan_start, candidate + 1)
    ]
    first_crossing = next(
        index for index, count in enumerate(scan_counts) if count > threshold
    )
    non_monotonic = any(
        right < left for left, right in zip(scan_counts, scan_counts[1:])
    )
    if first_crossing != len(scan_counts) - 1 or non_monotonic:
        if scan_start != 0:
            raise ValueError("cannot prove minimal prefix for non-monotonic tokenizer")
        candidate = first_crossing

    prompt, token_ids = encode_units(candidate)
    if (
        len(encode_units(candidate - 1)[1]) > threshold
        or not threshold < len(token_ids) <= maximum
        or encode(prompt) != token_ids
    ):
        raise ValueError("tokenizer did not produce a deterministic valid boundary")
    return prompt, token_ids


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--tokenizer-path", required=True, type=Path)
    parser.add_argument("--threshold", required=True, type=int)
    parser.add_argument("--context-limit", required=True, type=int)
    parser.add_argument("--output-allowance", required=True, type=int)
    parser.add_argument("--fixture", action="store_true")
    arguments = parser.parse_args()
    if arguments.fixture:
        marker = arguments.tokenizer_path / "fixture-tokenizer.json"
        if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")) != {
            "schema_version": "vllm-dlc-fixture-whitespace-tokenizer/v1"
        }:
            return 20
        encode = lambda value: list(range(1, len(value.split()) + 1))
    else:
        try:
            from transformers import AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                str(arguments.tokenizer_path),
                local_files_only=True,
                trust_remote_code=False,
            )
        except Exception:
            return 20
        encode = lambda value: tokenizer.encode(value, add_special_tokens=False)
    maximum = arguments.context_limit - arguments.output_allowance
    try:
        prompt, token_ids = build_long_prefix(
            encode, arguments.threshold, maximum
        )
    except (StopIteration, ValueError):
        return 20
    token_bytes = json.dumps(token_ids, separators=(",", ":")).encode("utf-8")
    print(json.dumps({
        "context_limit": arguments.context_limit,
        "output_allowance": arguments.output_allowance,
        "prompt": prompt,
        "prompt_digest": sha256(prompt.encode("utf-8")),
        "prompt_token_count": len(token_ids),
        "schema_version": "vllm-dlc-long-prefix-proof/v1",
        "threshold": arguments.threshold,
        "token_ids_digest": sha256(token_bytes),
    }, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
