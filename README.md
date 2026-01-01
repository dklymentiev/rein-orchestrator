# Dog - Process Manager with Real-time Control

## Quick Start (30 seconds)

```bash
# 1. Create YAML config
cat > workflow.yaml << EOFYAML
semaphore: 2
timeout: 60
blocks:
  - name: task-1
    command: "echo 'Task 1' && sleep 5"
    agent: agent-1
  - name: task-2
    command: "echo 'Task 2' && sleep 3"
    agent: agent-2
EOFYAML

# 2. Run workflow
python3 dog.py workflow.yaml

# 3. In another terminal, control it
./dog-cmd.sh status           # Current status
./dog-cmd.sh list             # All processes
./dog-cmd.sh pause task-1     # Pause by name
./dog-cmd.sh resume task-1    # Resume
./dog-cmd.sh cancel task-1    # Kill task
```

## Commands Reference

### Workflow Status
```bash
# List all active workflows
./dog-workflows.sh

# Show details for specific workflow
./dog-workflows.sh 20251230-165505

# Auto-detect single workflow
./dog-cmd.sh status
./dog-cmd.sh list

# Specify workflow GUID explicitly
./dog-cmd.sh 20251230-165505 status
./dog-cmd.sh 20251230-165505 list
```

### Process Control
```bash
# Pause single process by name
./dog-cmd.sh pause task-1
./dog-cmd.sh 20251230-165505 pause agent-1-step-2

# Resume paused process
./dog-cmd.sh resume task-1

# Cancel (kill) process
./dog-cmd.sh cancel task-1
./dog-cmd.sh kill task-1

# Get status of specific process
./dog-cmd.sh status task-1
```

### Monitoring

```bash
# Real-time monitoring (updates every 2 sec)
watch -n 2 './dog-workflows.sh'

# Or check logs directly
tail -f /tmp/dog-runs/run-20251230-165505/dog.log

# Count completions
grep "PROCESS COMPLETED" /tmp/dog-runs/run-20251230-165505/dog.log | wc -l

# Count failures
grep "PROCESS FAILED" /tmp/dog-runs/run-20251230-165505/dog.log | wc -l
```

## YAML Configuration

### Minimal Example
```yaml
semaphore: 1
timeout: 60

blocks:
  - name: my-task
    command: "bash script.sh"
```

### Complete Example
```yaml
semaphore: 3                    # Max 3 parallel processes
timeout: 300                    # 5 min total timeout

blocks:
  - name: phase-1-task-1
    command: "python3 process.py input.txt"
    agent: agent-1              # Optional: agent name for logging

  - name: phase-1-task-2
    command: "python3 process.py input.txt"
    agent: agent-1

  - name: phase-2-aggregator
    command: "python3 aggregate.py output.txt"
    agent: aggregator
    depends_on: [phase-1-task-1, phase-1-task-2]
```

## Common Issues

### "dog-cmd.sh list" returns empty
The list command shows in Dog's log, not stdout. Check log instead:
```bash
tail /tmp/dog-runs/run-20251230-165505/dog.log | grep "PROCESS"
```

### Multiple workflows detected
Specify GUID explicitly:
```bash
./dog-cmd.sh 20251230-165505 status
```

## Performance

- Tested: 111 tasks in 59 seconds (1.88 tasks/sec)
- Max parallelism: 10 concurrent processes
- Memory: ~30MB base + 5-10MB per 100 tasks
