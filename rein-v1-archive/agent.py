#!/usr/bin/env python3
"""
Generic Agent - executes 10 iterations of work with optional error simulation
Supports error modes: network-timeout, permission-denied, write-failure
Writes structured logs [TIMESTAMP] | [LEVEL] | [SECTION] | message
Always writes result file in JSON format
"""
import sys
import json
import time
import random
import os
import traceback
from datetime import datetime
from pathlib import Path

def write_log(log_file, level, section, message):
    """Write message to log file with structured format: [TIMESTAMP] | [LEVEL] | [SECTION] | message"""
    try:
        with open(log_file, 'a') as f:
            timestamp = datetime.utcnow().isoformat()
            f.write(f"{timestamp} | [{level}] | {section} | {message}\n")
            f.flush()
    except Exception as e:
        print(f"[Log Error] {e}", flush=True)

def write_result_file(result_dir, agent_name, result_data):
    """Write result file in JSON format to {result_dir}/{agent_name}.result"""
    try:
        result_file = os.path.join(result_dir, f"{agent_name}.result")
        with open(result_file, 'w') as f:
            json.dump(result_data, f, indent=2)
            f.flush()
        return result_file
    except Exception as e:
        print(f"[Result Error] Failed to write result file: {e}", flush=True)
        return None

def simulate_network_timeout(iteration, log_file):
    """Simulate network timeout error on iteration 5"""
    if iteration == 5:
        write_log(log_file, "WARN", "ITERATION", "5/10 | Simulating network timeout...")
        time.sleep(5)
        write_log(log_file, "ERROR", "ITERATION", "5/10 | ConnectionError: Network timeout after 5s")
        raise ConnectionError("Network timeout after 5s")

def simulate_permission_denied(iteration, log_file):
    """Simulate permission denied error on iteration 7"""
    if iteration == 7:
        write_log(log_file, "WARN", "ITERATION", "7/10 | Simulating permission denied...")
        try:
            # Try to write to read-only directory
            test_file = "/root/.test-write-agent"
            with open(test_file, 'w') as f:
                f.write("test")
        except PermissionError as e:
            write_log(log_file, "ERROR", "ITERATION", f"7/10 | PermissionError: {str(e)}")
            raise
        except Exception as e:
            write_log(log_file, "ERROR", "ITERATION", f"7/10 | PermissionError: {str(e)}")
            raise PermissionError(f"Permission denied: {str(e)}")

def simulate_write_failure(iteration, log_file):
    """Simulate write failure error on iteration 6"""
    if iteration == 6:
        write_log(log_file, "WARN", "ITERATION", "6/10 | Simulating write failure...")
        result_file = os.path.join("/tmp", "write-test-agent.tmp")
        try:
            # Try to write, then simulate failure
            with open(result_file, 'w') as f:
                f.write("partial")
                # Simulate disk full by raising IOError
                raise IOError("Disk full or write error")
        except IOError as e:
            write_log(log_file, "ERROR", "ITERATION", f"6/10 | IOError: {str(e)}")
            raise

def main():
    if len(sys.argv) < 2:
        print("Usage: agent.py <agent_name> [duration] [--error {network-timeout|permission-denied|write-failure}]")
        sys.exit(1)

    agent_name = sys.argv[1]
    params = sys.argv[2:] if len(sys.argv) > 2 else []

    # Parse parameters
    duration_per_iteration = 1.0
    error_mode = None

    for i, param in enumerate(params):
        if param == "--error" and i + 1 < len(params):
            error_mode = params[i + 1]
        else:
            try:
                total_duration = float(param)
                duration_per_iteration = total_duration / 10
            except:
                pass

    # Get log directory from environment
    log_dir = os.environ.get('DOG_LOG_DIR', '/tmp/dog-logs')
    log_file = os.path.join(log_dir, f"{agent_name}.log")

    # Create log directory if needed
    os.makedirs(log_dir, exist_ok=True)

    # Startup
    start_time = datetime.utcnow()
    write_log(log_file, "INFO", "STARTED", f"Agent {agent_name} starting | duration_per_iter={duration_per_iteration:.1f}s | error_mode={error_mode}")
    print(f"[Agent] {agent_name} starting", flush=True)

    results = []
    iterations_completed = 0
    error_occurred = None
    error_traceback = None
    exit_code = 0

    # 10 iterations
    try:
        for iteration in range(1, 11):
            progress_percent = iteration * 10

            # Simulate work
            time.sleep(duration_per_iteration)

            # Trigger error simulation if enabled
            if error_mode == "network-timeout":
                simulate_network_timeout(iteration, log_file)
            elif error_mode == "permission-denied":
                simulate_permission_denied(iteration, log_file)
            elif error_mode == "write-failure":
                simulate_write_failure(iteration, log_file)

            # Generate properties for this iteration
            properties = {
                "iteration": iteration,
                "progress": progress_percent,
                "timestamp": datetime.utcnow().isoformat(),
                "items_processed": iteration * 10,
                "status": "processing" if iteration < 10 else "complete"
            }

            # Log iteration
            write_log(log_file, "INFO", "ITERATION", f"{iteration}/10 | progress={progress_percent}% | items={properties['items_processed']}")

            # Output progress in JSON format
            output = {
                "agent": agent_name,
                "type": "progress",
                "progress": progress_percent,
                "properties": properties
            }

            print(f"[JSON] {json.dumps(output)}", flush=True)

            results.append(properties)
            iterations_completed = iteration

    except Exception as e:
        # Catch all exceptions
        error_occurred = str(e)
        error_type = type(e).__name__
        error_traceback = traceback.format_exc()

        write_log(log_file, "ERROR", "EXCEPTION", f"{error_type}: {error_occurred}")
        write_log(log_file, "ERROR", "TRACEBACK", error_traceback.replace('\n', ' | '))

        exit_code = 1
        print(f"[Agent] {agent_name} failed: {error_type}: {error_occurred}", flush=True)
    else:
        error_type = None
        error_traceback = None

    # Calculate elapsed time
    end_time = datetime.utcnow()
    elapsed_seconds = (end_time - start_time).total_seconds()

    # Write completion/failure log
    if exit_code == 0:
        write_log(log_file, "INFO", "COMPLETED", f"All 10 iterations finished successfully | elapsed={elapsed_seconds:.1f}s")
        print(f"[Agent] {agent_name} completed successfully!", flush=True)
    else:
        write_log(log_file, "ERROR", "COMPLETED", f"Failed after {iterations_completed} iterations | error={error_occurred} | elapsed={elapsed_seconds:.1f}s")
        print(f"[Agent] {agent_name} failed after {iterations_completed} iterations!", flush=True)

    # Create result file (ALWAYS, even on error)
    result_data = {
        "name": agent_name,
        "timestamp": start_time.isoformat(),
        "exit_code": exit_code,
        "duration_seconds": elapsed_seconds,
        "iterations_completed": iterations_completed,
        "error": error_occurred,
        "error_type": error_type,
        "error_traceback": error_traceback,
        "properties": results
    }

    result_file = write_result_file(log_dir, agent_name, result_data)
    if result_file:
        write_log(log_file, "INFO", "RESULT", f"Result file written: {result_file}")
        print(f"[Agent] Result file: {result_file}", flush=True)

    # Output final result in JSON
    final_output = {
        "agent": agent_name,
        "type": "final_result",
        "exit_code": exit_code,
        "status": "success" if exit_code == 0 else "failed",
        "iterations_completed": iterations_completed,
        "elapsed_seconds": elapsed_seconds,
        "error": error_occurred
    }

    print(f"[JSON] {json.dumps(final_output)}", flush=True)

    return exit_code

if __name__ == "__main__":
    sys.exit(main())
