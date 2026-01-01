# Agent-PM2 Dog - Enhanced Features

**Status:** Proposed
**Date:** 2025-12-30
**Priority:** High

## Requirements Overview

### 1. Process Control (Pause/Resume)

#### Pause Entire Workflow
```bash
# CLI command
dog.py --config workflow.yaml --pause

# Effect:
# - Stop spawning new tasks immediately
# - Keep currently running processes alive
# - Mark "waiting" processes as "paused"
# - Dog enters pause state (UI shows [PAUSED])
```

#### Resume Entire Workflow
```bash
# CLI command
dog.py --config workflow.yaml --resume run-20251230-105927

# Effect:
# - Resume from saved state directory
# - Continue spawning pending tasks respecting dependencies
# - Restore "paused" processes to "waiting" if conditions met
```

#### Pause Single Process
```yaml
blocks:
  - name: expensive-validation
    command: python3 /path/to/validator.py
    blocking_pause: true    # If paused, dependents cannot proceed

  - name: optional-notify
    command: python3 /path/to/notify.py
    blocking_pause: false   # Can be paused without affecting dependents
```

**Effect:**
- Paused process: stays "paused" state, no spawn
- If `blocking_pause: true`: dependents stuck in "waiting"
- If `blocking_pause: false`: dependents can proceed

### 2. Error Simulation & Handling

#### Agent.py Test Modes

```bash
# Normal mode
python3 agent.py agent-001 30

# Error simulation modes
python3 agent.py agent-001 30 --error network-timeout
python3 agent.py agent-001 30 --error permission-denied
python3 agent.py agent-001 30 --error write-failure
```

#### Error Types Implemented

1. **network-timeout**: Simulate 5s network access delay, then fail with ConnectionError
2. **permission-denied**: Fail trying to write to read-only directory
3. **write-failure**: Partial write, then raise IOError
4. **random-crash**: Simulate unpredictable process crash (SIGSEGV)

#### Exception Handling Guarantees

```python
# Every error must be:
# 1. Caught at process level
# 2. Logged with full traceback to {log_dir}/{name}.log
# 3. Signal to dog.py via exit code (!= 0)
# 4. Result file created with error metadata

# Log format example:
[2025-12-30T11:05:23.123456] | [ERROR] | agent-001 | iteration-3 | ConnectionError: Network timeout after 5s
Traceback:
  File "agent.py", line 45, in simulate_network_work
    requests.get("http://...", timeout=5)
  ...
```

### 3. Result Verification (Criteria of Acceptance)

#### Minimal Acceptance Criteria

Dog verifies block success by checking:

```python
result_file = f"{log_dir}/{block_name}.result"

# Criteria:
if os.path.exists(result_file) and os.path.getsize(result_file) > 0:
    process.status = "done"
else:
    process.status = "failed"

# Note: NO content validation - accept any non-empty file
```

#### Result File Format

Agent must create `{log_dir}/{name}.result` containing JSON:

```json
{
  "name": "agent-001",
  "timestamp": "2025-12-30T11:05:23.123456",
  "exit_code": 0,
  "duration_seconds": 30.5,
  "iterations_completed": 10,
  "error": null
}
```

Or on error:

```json
{
  "name": "agent-001",
  "timestamp": "2025-12-30T11:05:23.123456",
  "exit_code": 1,
  "duration_seconds": 15.3,
  "iterations_completed": 5,
  "error": "ConnectionError: Network timeout after 5s"
}
```

### 4. Logging & Observability

#### Agent Log Format

```
[TIMESTAMP] | [LEVEL] | [SECTION] | message
```

Example:
```
2025-12-30T11:05:23.123456 | [INFO] | STARTED | Agent agent-001 starting
2025-12-30T11:05:26.234567 | [INFO] | ITERATION | 1/10 | progress=10%
2025-12-30T11:05:29.345678 | [ERROR] | ITERATION | 2/10 | ConnectionError: timeout
2025-12-30T11:05:29.456789 | [INFO] | COMPLETED | 2 iterations, exit_code=1
```

#### Dog Log Enhancements

```
[TIMESTAMP] | [EVENT_TYPE] | [DETAILS]
```

Examples:
```
2025-12-30T11:05:23.123456 | PAUSE_REQUESTED | workflow paused
2025-12-30T11:05:24.234567 | PAUSE_ACTIVE | paused processes: agent-001, agent-003
2025-12-30T11:05:45.345678 | RESUME_REQUESTED | resuming workflow
2025-12-30T11:05:45.456789 | RESULT_VERIFICATION | agent-001 | result_file exists | status=done
2025-12-30T11:05:46.567890 | RESULT_VERIFICATION_FAILED | agent-005 | result_file missing | status=failed
```

---

## Implementation Checklist

### Phase 1: Error Handling & Result Verification
- [ ] Add `--error-mode` parameter to agent.py
- [ ] Implement network-timeout simulation
- [ ] Implement permission-denied simulation
- [ ] Implement write-failure simulation
- [ ] Create result file in agent.py (always, success or failure)
- [ ] Write result file in JSON format
- [ ] Update agent logging to [LEVEL] format
- [ ] Test: Run single agent with each error mode, verify result file created
- [ ] Test: Verify dog.py reads result file and marks process status correctly

### Phase 2: Process-Level Pause/Resume
- [ ] Add `pause_single` command to dog.py CLI
- [ ] Add `blocking_pause` field to YAML config parser
- [ ] Implement pause mechanism: set process.status = "paused"
- [ ] Implement blocking logic: check if paused process blocks dependents
- [ ] Update spawn logic: skip "paused" processes, check blocking dependents
- [ ] Update UI: Show [PAUSED] status in table
- [ ] Test: Pause single process, verify dependents handled correctly
- [ ] Test: Resume single process, verify spawning resumes

### Phase 3: Workflow-Level Pause/Resume
- [ ] Add `--pause` CLI flag to pause workflow mid-execution
- [ ] Add `--resume RUN_ID` CLI flag to resume from saved state
- [ ] Implement pause state save: mark timestamp, save pending list
- [ ] Implement resume state load: restore pending, completed, running from DB
- [ ] Update UI: Show [PAUSED] in header when paused
- [ ] Update dog.log: Log PAUSE_REQUESTED, PAUSE_ACTIVE, RESUME_REQUESTED
- [ ] Test: Pause workflow, verify no new processes spawn
- [ ] Test: Resume workflow, verify continues from pause point

### Phase 4: Result Verification Integration
- [ ] Modify `_monitor_process()` to check result file after process exits
- [ ] Add logic: if exit_code==0 AND result_file exists → status="done"
- [ ] Add logic: if exit_code!=0 OR result_file missing → status="failed"
- [ ] Update dog.log: Log RESULT_VERIFICATION results
- [ ] Test: Run workflow, verify result file checks work
- [ ] Test: Run agent with error, verify dog detects failure

### Phase 5: Error Scenarios & Testing
- [ ] Create test workflow with network-timeout errors
- [ ] Create test workflow with permission-denied errors
- [ ] Create test workflow with mixed success/failure
- [ ] Run end-to-end test: all 100 agents with error modes
- [ ] Verify: All errors logged with full traceback
- [ ] Verify: All result files created
- [ ] Verify: Dog correctly marks processes as done/failed

### Phase 6: Documentation & Cleanup
- [ ] Update README.md with pause/resume examples
- [ ] Update README.md with error simulation guide
- [ ] Add EXAMPLES.md for common workflows
- [ ] Verify: No emoji in any output
- [ ] Verify: All logging consistent format

---

## Testing Scenarios

### Scenario 1: Single Agent Error
```yaml
blocks:
  - name: agent-network-fail
    command: python3 agent.py agent-network-fail 30 --error network-timeout
```
**Expected:**
- Process fails after ~5s
- Result file created with error metadata
- Dog marks as "failed"
- Log shows full traceback

### Scenario 2: Mixed Success/Failure
```yaml
blocks:
  - name: agent-001
    command: python3 agent.py agent-001 30
  - name: agent-002
    command: python3 agent.py agent-002 30 --error permission-denied
  - name: agent-003
    command: python3 agent.py agent-003 30
    depends_on: [agent-001, agent-002]
```
**Expected:**
- agent-001: success (done)
- agent-002: failure (failed)
- agent-003: Depend on failed process? → should wait for agent-001 only, or fail? (TBD)

### Scenario 3: Pause/Resume with Blocking Dependencies
```yaml
blocks:
  - name: validator
    command: python3 agent.py validator 30
    blocking_pause: true
  - name: processor
    command: python3 agent.py processor 30
    depends_on: [validator]
  - name: notifier
    command: python3 agent.py notifier 30
    blocking_pause: false
```
**Expected:**
- Pause validator → processor stuck waiting, notifier can proceed
- Resume validator → processor spawns

### Scenario 4: Workflow Pause/Resume
**Steps:**
1. Start 100-agent workflow
2. After 30s, pause workflow
3. Verify: No new processes spawn
4. After 10s pause, resume
5. Verify: Workflow continues from where it left off

---

## Notes

- **Backward Compatibility:** All new features are optional, existing workflows should work unchanged
- **Database Changes:** May need to add "paused" status to process table
- **CLI Design:** Consider interactive pause/resume commands (STDIN based)
- **Future:** Consider signal-based pause (SIGUSR1) instead of CLI flags

