#!/usr/bin/env python3
"""
Mock agent for pipeline testing.
Reads input file, appends agent metadata, writes to output file.

Usage:
  python3 mock-agent.py <input_file> <agent_name> <step_number> <output_file>

Example:
  python3 mock-agent.py input.txt agent-1 1 output.txt
"""

import sys
import os
from datetime import datetime


def main():
    if len(sys.argv) != 5:
        print("Usage: mock-agent.py <input_file> <agent_name> <step_number> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    agent_name = sys.argv[2]
    step_number = sys.argv[3]
    output_file = sys.argv[4]

    try:
        # Read input file (or create if doesn't exist)
        if os.path.exists(input_file):
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = ""

        # Generate timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Append agent metadata
        metadata = f"[{timestamp}] {agent_name} step {step_number}\n"
        content += metadata

        # Write to output file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"OK: {agent_name} step {step_number} -> {output_file}")
        sys.exit(0)

    except Exception as e:
        print(f"ERROR: {agent_name} step {step_number}: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
