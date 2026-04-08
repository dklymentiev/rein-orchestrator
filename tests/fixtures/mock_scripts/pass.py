#!/usr/bin/env python3
"""Deterministic pass-through mock. No delays, no randomness."""
import sys, json, os

ctx = json.load(sys.stdin)
output_file = ctx['output_file']
name = ctx.get('block_config', {}).get('name', '?')
run_count = ctx.get('run_count', 0)

os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, 'w') as f:
    json.dump({
        "result": f"{name} ok run={run_count}",
        "status": "ok",
        "approved": True
    }, f)
