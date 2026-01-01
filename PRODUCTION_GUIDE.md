# Dog Production Guide - Workflow Visibility & Monitoring

**Date:** 2025-12-31
**Status:** Implemented (MVP production tools)
**Phase:** Tier 1 - Production Readiness

## Overview

Dog now includes comprehensive visibility tools for production use. These tools answer the core question: **"What workflows ran, when, and what were the results?"**

## Quick Tools

### 1. Quick Status Check - `dog-status.sh`

Shows the last 2 workflows at a glance.

```bash
./dog-status.sh
```

**Output:**
```
Dog Status - Last 2 Workflows
════════════════════════════════════════════════

[LATEST] 20251231-125718
  ✗ Status: FAILED
  Time: 2025-12-31T12:57:18.871196
  Result: 0/5 agents completed, 5 failed

[PREVIOUS] 20251230-201734
  ✓ Status: COMPLETE
  Time: 2025-12-30T20:17:34.216001
  Result: 11/11 agents completed, 0 failed

════════════════════════════════════════════════
For details:
  ./dog-history.sh 10         # Show history (last 10)
  ./dog-history.sh 10 latest  # Show latest details
```

**Use when:** You just ran a workflow and want to check "did it work?"

### 2. Full History - `dog-history.sh`

Shows workflow history with filtering and detailed results.

**Basic usage (show last 5 runs):**
```bash
./dog-history.sh 5
```

**Output:**
```
Dog Workflow History - Last 5 Executions
════════════════════════════════════════════════════════════

[20251231-125718] 12:57:18  ✗ FAILED   0/5 agents  Time: 4s
[20251230-201734] 20:17:34  ✓ COMPLETE 11/11 agents Time: 1206s
[20251230-192431] 19:24:32  ✓ COMPLETE 11/11 agents Time: 1248s
```

**Detailed view (latest run):**
```bash
./dog-history.sh 10 latest
```

**Detailed view (specific run):**
```bash
./dog-history.sh 10 20251231-125718
```

**Detailed output includes:**
- **Metadata:** Run configuration, timing, agent count
- **Summary:** Final statistics (completed, failed, total agents)
- **Process Results:** SQLite database query results
- **Last Log Entries:** Recent execution events
- **Agent Logs:** List of individual agent logs with sizes
- **Log Sample:** First 10 lines of first agent's log

## Data Structure

Workflow runs are stored in `/tmp/dog-runs/` with the following structure:

```
/tmp/dog-runs/
├── run-20251231-125718/           # Run directory (YYYYMMDD-HHMMSS format)
│   ├── dog.db                     # SQLite database with process state
│   ├── dog.log                    # Main orchestrator log
│   ├── metadata.json              # Run configuration and metadata
│   ├── summary.json               # Final execution summary
│   └── logs/                      # Individual agent logs
│       ├── analyst-1.log
│       ├── processor-1.log
│       └── ...
└── run-20251230-201734/           # Previous run
    └── ...
```

### Key Files Explained

**metadata.json** - Run configuration
```json
{
  "start_time": "2025-12-31T12:57:18.871196",
  "run_id": "20251231-125718",
  "total_agents": 5,
  "max_parallel": 3,
  "end_time": "2025-12-31T12:57:22.671878"
}
```

**summary.json** - Final results
```json
{
  "run_id": "20251231-125718",
  "total_agents": 5,
  "completed": 0,
  "failed": 5,
  "start_time": "2025-12-31T12:57:18.871196",
  "end_time": "2025-12-31T12:57:22.671878"
}
```

**dog.log** - Event stream
```
2025-12-31T12:57:18.871386 | DOG STARTED | run_id=20251231-125718
2025-12-31T12:57:18.932435 | SOCKET SERVER | listening on /tmp/dog-20251231-125718.sock
2025-12-31T12:57:18.996041 | PROCESS STARTED | task-1-analyze[310c6bb1] | pid=2613166
2025-12-31T12:57:20.482491 | PROCESS FAILED | task-3-validate[1af314b2] | exit_code=0
2025-12-31T12:57:22.672430 | DOG FINISHED | completed=0 | failed=5 | total=5
```

## Common Usage Patterns

### Pattern 1: Check Last Run (Quick)
```bash
./dog-status.sh
```
Best for: "Did my last task work?"

### Pattern 2: View Recent History
```bash
./dog-history.sh 10
```
Best for: "What has been running lately?"

### Pattern 3: Analyze Failed Run
```bash
./dog-history.sh 10 20251231-125718
```
Shows: Full logs, agent output, exit codes, error details

### Pattern 4: Compare Runs
```bash
./dog-history.sh 5           # Show last 5
./dog-history.sh 10 RUN_ID   # Get details of specific one
```

### Pattern 5: Monitor Background Daemon (Future)
```bash
watch -n 1 './dog-status.sh'  # Refresh every second
```
(Will work when Dog Daemon is implemented)

## Status Indicators

### Status Colors & Symbols

| Symbol | Status | Meaning |
|--------|--------|---------|
| ✓ | COMPLETE | All agents finished successfully |
| ✗ | FAILED | One or more agents failed |
| ⟳ | RUNNING | Workflow still executing |

### Color Codes

| Color | Usage |
|-------|-------|
| GREEN | Successful completion (✓) |
| RED | Failed workflows or agents (✗) |
| YELLOW | Running workflows (⟳) |
| CYAN | Headers and labels |
| BLUE | Metadata and details |

## Troubleshooting

### Issue: "scripts not found"
```bash
cd /server/scripts/agent-pm2-dog
./dog-status.sh   # Make sure you're in the right directory
```

### Issue: "No runs to display"
```bash
# Check if /tmp/dog-runs exists
ls -la /tmp/dog-runs/

# Run a workflow first
python3 dog.py example.yaml
```

### Issue: "Database read error" in detailed view
- The SQLite database may be locked or in a different format
- All other information (logs, metadata, summary) is still available
- This is not critical - you can still see results in the log files

## Next Steps (Production Enhancements)

### Tier 2.5: Dog Daemon (Queued)
Persistent background service that:
- Maintains task queue (SQLite)
- Accepts workflow submissions via HTTP API
- Executes with semaphore control
- Tracks results persistently
- See: `../dog-daemon-rfc.md`

### Tier 3.2: Nested Workflows (Proposed)
Composite workflow blocks:
- Workflows containing sub-workflows
- For-loop expansion for batch processing
- Matrix execution for multi-dimensional testing
- See: `../dog-nested-workflows.txt`

### Tier 4: Web Dashboard (Future)
- Real-time execution visualizer
- Historical trend analysis
- Performance metrics
- Error analysis and patterns

## Integration with Monitoring

These tools can be integrated into:

```bash
# Cron job for periodic status check
0 * * * * /server/scripts/agent-pm2-dog/dog-status.sh >> /var/log/dog-status.log

# Telegram alerts (via admin-bot)
/server/scripts/admin-bot/telegram-admin.sh "Dog Status: $(./dog-status.sh)"

# Memory system logging (worklogs)
mem register agent-pm2-dog-001 "$(./dog-history.sh 10)" "type:worklog"
```

## Performance Notes

- **dog-status.sh:** ~50ms (reads 2 directories, parses 2 JSON files)
- **dog-history.sh (list):** ~100ms (reads last N directories)
- **dog-history.sh (detail):** ~500ms (full parsing with SQLite)
- **Safe for cron:** Yes, both scripts are lightweight

## File Locations

| Script | Path |
|--------|------|
| Status tool | `/server/scripts/agent-pm2-dog/dog-status.sh` |
| History tool | `/server/scripts/agent-pm2-dog/dog-history.sh` |
| Data directory | `/tmp/dog-runs/` |
| Main orchestrator | `/server/scripts/agent-pm2-dog/dog.py` |
| This guide | `/server/scripts/agent-pm2-dog/PRODUCTION_GUIDE.md` |

## Summary

With `dog-status.sh` and `dog-history.sh`, Dog now provides complete visibility into:

✓ What workflows are running
✓ When they ran (start/end times)
✓ How long they took (duration)
✓ Success/failure status
✓ How many agents completed/failed
✓ Detailed logs and debugging info

**Ready for production use!**
