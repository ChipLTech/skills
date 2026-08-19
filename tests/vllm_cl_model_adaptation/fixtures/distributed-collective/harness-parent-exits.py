#!/usr/bin/env python3
import json
import subprocess
import sys

subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
print(json.dumps({"rank_results": [{"rank": 0, "exit_code": 0}, {"rank": 1, "exit_code": 0}]}))
