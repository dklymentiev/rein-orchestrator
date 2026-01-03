#!/usr/bin/env python3
"""
Mock agent for testing - receives task, waits 5 seconds, returns result
"""
import sys
import json
import time
from datetime import datetime

def main():
    if len(sys.argv) < 2:
        print("Usage: mock_agent.py <task_name> [duration_seconds]")
        sys.exit(1)

    task_name = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print(f"[Agent] Received task: {task_name}")
    print(f"[Agent] Processing for {duration} seconds...")

    # Simulate work with progress every 10%
    step_duration = duration / 10  # Sleep this long per progress step
    for i in range(10):
        progress = (i + 1) * 10  # 10%, 20%, 30%, ... 100%
        print(f"[Agent] {task_name}: {progress}% complete", flush=True)
        time.sleep(step_duration)
    
    # Return result
    result = {
        "task": task_name,
        "status": "completed",
        "timestamp": datetime.utcnow().isoformat(),
        "data": f"Results from {task_name}"
    }
    
    print(f"[Agent] Task '{task_name}' completed!")
    print(f"[Agent] Result: {json.dumps(result, indent=2)}")

if __name__ == "__main__":
    main()
