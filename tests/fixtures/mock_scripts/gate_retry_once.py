#!/usr/bin/env python3
"""Deterministic gate: always fails on run 0, always passes on run 1+.
This gives predictable retry behavior: exactly 1 retry per gate.

Small fixed delay (0.1s) to give orchestrator time for routing evaluation."""

import json
import os
import sys
import time

ctx = json.load(sys.stdin)
time.sleep(0.1)
output_file = ctx["output_file"]
name = ctx.get("block_config", {}).get("name", "?")
run_count = ctx.get("run_count", 0)

verdict = "REVISE" if run_count == 0 else "PASS"
approved = run_count > 0

os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, "w") as f:
    json.dump({"result": f"VERDICT: {verdict}", "verdict": verdict, "approved": approved, "run": run_count + 1}, f)

print(f"VERDICT: {verdict}")
