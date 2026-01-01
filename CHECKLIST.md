# Agent-PM2 Dog - Implementation Checklist

**Project GUID:** agent-pm2-dog-001
**Date Created:** 2025-12-30
**Status:** Proposed

---

## PHASE 1: Error Handling & Result Verification

### Subtask 1.1: Add Error Simulation to agent.py
- [ ] Add `--error-mode` CLI parameter
- [ ] Parameter values: `none`, `network-timeout`, `permission-denied`, `write-failure`
- [ ] Default: `none` (normal operation)

### Subtask 1.2: Implement network-timeout Simulation
- [ ] Sleep for 5 seconds during iteration
- [ ] Raise `ConnectionError("Network timeout after 5s")`
- [ ] Catch and log full traceback
- [ ] Write result file with error metadata

### Subtask 1.3: Implement permission-denied Simulation
- [ ] Try to write to `/root/.test-write` (read-only)
- [ ] Raise `PermissionError("Permission denied")`
- [ ] Catch and log full traceback
- [ ] Write result file with error metadata

### Subtask 1.4: Implement write-failure Simulation
- [ ] Try to write partial data, then close file
- [ ] Raise `IOError("Disk full")`
- [ ] Catch and log full traceback
- [ ] Write result file with error metadata

### Subtask 1.5: Create Result File
- [ ] Always create `{log_dir}/{name}.result` file
- [ ] JSON format with: name, timestamp, exit_code, duration, iterations, error
- [ ] Create on success AND on failure
- [ ] At least 1 byte (non-empty check in dog.py)

### Subtask 1.6: Update Agent Logging Format
- [ ] Change format to: `[TIMESTAMP] | [LEVEL] | [SECTION] | message`
- [ ] LEVEL: INFO, ERROR, WARNING
- [ ] SECTION: STARTED, ITERATION, COMPLETED, ERROR
- [ ] Update all log statements

### Subtask 1.7: Test Error Handling
- [ ] Run agent with `--error network-timeout`, verify result file created
- [ ] Run agent with `--error permission-denied`, verify exit_code != 0
- [ ] Run agent with `--error write-failure`, verify traceback in log
- [ ] Verify result files JSON valid

---

## PHASE 2: Process-Level Pause/Resume

### Subtask 2.1: Add YAML blocking_pause Field
- [ ] Parse `blocking_pause: true/false` from config
- [ ] Default: `true` (safer default)
- [ ] Store in Process dataclass

### Subtask 2.2: Add pause_single() Method to ProcessManager
- [ ] Accept process name
- [ ] Set process.status = "paused"
- [ ] Save to DB
- [ ] Do not send SIGTERM (keep process alive)

### Subtask 2.3: Add resume_single() Method to ProcessManager
- [ ] Accept process name
- [ ] Set process.status = "waiting" if dependencies met
- [ ] Mark for respawning
- [ ] Check blocking_pause on dependents

### Subtask 2.4: Update spawn_process() Logic
- [ ] Skip "paused" processes
- [ ] Check if any dependency has `blocking_pause: true` AND is paused
- [ ] If blocking, don't spawn dependent
- [ ] If non-blocking, spawn dependent

### Subtask 2.5: Add Interactive Pause Command (stdin)
- [ ] While workflow running, listen on stdin
- [ ] Command: `pause agent-001` → pause specific process
- [ ] Command: `resume agent-001` → resume specific process
- [ ] Command: `status` → show paused processes
- [ ] Don't block main workflow loop

### Subtask 2.6: Update UI to Show Paused Status
- [ ] Add "paused" status color in render_table()
- [ ] Show [PAUSED] in status column
- [ ] Update title if any processes paused

### Subtask 2.7: Test Single Process Pause/Resume
- [ ] Run workflow, pause middle process
- [ ] Verify dependents not spawned
- [ ] Resume, verify dependents spawn
- [ ] Test blocking_pause: true/false behavior

---

## PHASE 3: Workflow-Level Pause/Resume

### Subtask 3.1: Add --pause CLI Flag
- [ ] Accept `--pause` during workflow execution
- [ ] Set manager.paused = True
- [ ] Stop spawning NEW tasks only
- [ ] Keep running tasks alive

### Subtask 3.2: Add --resume CLI Flag
- [ ] Accept `--resume RUN_ID` to resume from saved state
- [ ] Load from `/tmp/dog-runs/run-RUN_ID/`
- [ ] Load state from DB
- [ ] Reconstruct pending task list

### Subtask 3.3: Implement Pause State Save
- [ ] On pause, mark timestamp in dog.log
- [ ] Write pending tasks to text file
- [ ] Write paused processes list
- [ ] Write running processes list

### Subtask 3.4: Implement Resume State Load
- [ ] Read pending tasks from file
- [ ] Restore running processes from DB
- [ ] Check which already completed
- [ ] Recalculate phases for remaining

### Subtask 3.5: Update Workflow Loop for Pause
- [ ] Check `self.manager.paused` in run_workflow()
- [ ] If paused, sleep instead of spawning
- [ ] Still monitor running processes
- [ ] Allow resume signal to unpause

### Subtask 3.6: Update UI for Pause State
- [ ] Show [PAUSED] in title
- [ ] Show pause timestamp
- [ ] Show pending tasks count
- [ ] Show resume options in help text

### Subtask 3.7: Test Workflow Pause/Resume
- [ ] Run 100-agent workflow
- [ ] Pause after 30s
- [ ] Verify no new processes spawn
- [ ] Resume, verify continues
- [ ] Check consistency (no duplicate spawns)

---

## PHASE 4: Result Verification Integration

### Subtask 4.1: Check Result File in _monitor_process()
- [ ] After process exits, check for result file
- [ ] Path: `{self.manager.log_dir}/{name}.result`
- [ ] Check `os.path.exists()` AND `os.path.getsize() > 0`

### Subtask 4.2: Implement Success Logic
- [ ] If exit_code == 0 AND result_file exists → status = "done"
- [ ] Save to DB
- [ ] Log RESULT_VERIFICATION success

### Subtask 4.3: Implement Failure Logic
- [ ] If exit_code != 0 → status = "failed"
- [ ] If result_file missing AND exit_code == 0 → status = "failed"
- [ ] Save to DB
- [ ] Log RESULT_VERIFICATION failure reason

### Subtask 4.4: Add Result Verification Logging
- [ ] Log event: `RESULT_VERIFICATION | {name} | result_file={'exists'|'missing'} | status={'done'|'failed'}`
- [ ] Include exit_code in log
- [ ] Include file path

### Subtask 4.5: Test Integration with agent.py
- [ ] Run agent with success, verify dog reads result file
- [ ] Run agent with error, verify result file created with error
- [ ] Verify dog marks process correctly

### Subtask 4.6: Test Mixed Results
- [ ] Run workflow with 50% success, 50% failure
- [ ] Verify summary shows correct counts
- [ ] Verify result files present for all

---

## PHASE 5: Error Scenarios & Testing

### Subtask 5.1: Create Test Workflow with network-timeout
- [ ] YAML: 10 agents, 3 with `--error network-timeout`
- [ ] Run workflow
- [ ] Verify 3 agents fail, 7 succeed
- [ ] Verify result files created for all

### Subtask 5.2: Create Test Workflow with permission-denied
- [ ] YAML: 5 agents with `--error permission-denied`
- [ ] Run workflow
- [ ] Verify all fail with PermissionError in logs
- [ ] Verify exit codes -1 or non-zero

### Subtask 5.3: Create Test Workflow with mixed errors
- [ ] YAML: network-timeout + permission-denied + success
- [ ] Run workflow
- [ ] Verify dog handles all correctly
- [ ] Verify summary accurate

### Subtask 5.4: Test 100-Agent Workflow with Errors
- [ ] Generate 100-agent config with 10% error rate
- [ ] Run full workflow
- [ ] Verify timeout still works
- [ ] Verify all 100 result files created
- [ ] Verify dog.log complete

### Subtask 5.5: Verify All Errors Logged
- [ ] Check all agent logs contain traceback
- [ ] Check dog.log contains PROCESS FAILED entries
- [ ] Verify RESULT_VERIFICATION events logged
- [ ] Verify timestamps consistent

### Subtask 5.6: Stress Test Pause/Resume with Errors
- [ ] Run workflow, introduce errors
- [ ] Pause during error phase
- [ ] Resume
- [ ] Verify error handling consistent
- [ ] Verify no deadlocks

---

## PHASE 6: Documentation & Cleanup

### Subtask 6.1: Update README.md
- [ ] Add "Error Simulation" section
- [ ] Add example: `agent.py ... --error network-timeout`
- [ ] Document result file format
- [ ] Document criteria for acceptance

### Subtask 6.2: Add EXAMPLES.md
- [ ] Example 1: Simple error simulation
- [ ] Example 2: Mixed success/failure workflow
- [ ] Example 3: Pause/resume workflow
- [ ] Example 4: blocking_pause behavior

### Subtask 6.3: Verify No Emoji
- [ ] Grep for emoji in dog.py, agent.py, FEATURES.md
- [ ] Ensure all output uses [TAGS] format
- [ ] Verify UI uses only ASCII characters

### Subtask 6.4: Verify Log Format Consistency
- [ ] Dog log: consistent timestamps, event types
- [ ] Agent log: consistent [LEVEL] [SECTION] format
- [ ] Result files: consistent JSON schema

### Subtask 6.5: Code Review & Cleanup
- [ ] Remove debug print statements
- [ ] Add docstrings to new methods
- [ ] Ensure error messages helpful
- [ ] Test on Python 3.8+ (compatibility)

### Subtask 6.6: Final Testing & Sign-off
- [ ] Run full 100-agent workflow with all features
- [ ] Verify pause/resume, errors, results
- [ ] Verify dog.log is complete and readable
- [ ] Verify all artifacts saved correctly

---

## Summary

**Total Implementation Tasks:** 37
**Total Testing Tasks:** 6
**Estimated Effort:** 60-80 development hours

**Dependency Order:**
1. Phase 1 (error handling) - Foundation
2. Phase 4 (result verification) - Uses Phase 1
3. Phase 2 (single pause/resume) - Independent
4. Phase 3 (workflow pause/resume) - Builds on Phase 2
5. Phase 5 (testing) - Uses all phases
6. Phase 6 (documentation) - Final cleanup

---

## Status Tracking

- [ ] Phase 1: Started/Completed (0%)
- [ ] Phase 2: Not started (0%)
- [ ] Phase 3: Not started (0%)
- [ ] Phase 4: Not started (0%)
- [ ] Phase 5: Not started (0%)
- [ ] Phase 6: Not started (0%)

**Overall Completion:** 0%
