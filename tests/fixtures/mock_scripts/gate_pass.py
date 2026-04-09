#!/usr/bin/env python3
"""Deterministic gate: always passes on first run. No retries."""

import json
import os
import sys

ctx = json.load(sys.stdin)
output_file = ctx["output_file"]
name = ctx.get("block_config", {}).get("name", "?")
run_count = ctx.get("run_count", 0)

os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, "w") as f:
    json.dump({"result": "VERDICT: PASS", "verdict": "PASS", "approved": True, "run": run_count + 1}, f)

print("VERDICT: PASS")
