#!/usr/bin/env python3
import json
import hashlib


def digest(value):
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()

print(json.dumps({
    "rank_results": [{"rank": 0, "exit_code": 0}, {"rank": 1, "exit_code": 0}],
    "primitive_results": [
        {"primitive": "all_reduce", "actual_digest": digest("all_reduce:[2,4]")},
        {"primitive": "moe_dispatch", "actual_digest": digest("moe_dispatch:[[0,1],[1,0]]")},
        {"primitive": "moe_combine", "actual_digest": digest("moe_combine:[3,7]")},
    ],
}))
