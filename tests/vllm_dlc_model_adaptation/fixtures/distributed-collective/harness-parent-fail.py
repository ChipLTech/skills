#!/usr/bin/env python3
import json
import sys

print(json.dumps({"rank_results": [{"rank": 0, "exit_code": 0}, {"rank": 1, "exit_code": 0}]}))
sys.exit(9)
