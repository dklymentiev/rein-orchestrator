# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.3.1] - 2026-04-04

Stability and hardening release. No API changes; 3.3.0 flows run unchanged.
Focus: make the orchestrator core robust enough for pre-release handoff.

### Fixed

- **#1166** Blocks no longer stuck in `waiting` after routing cascade -- pending re-evaluation now correctly re-queues cascade-invalidated blocks.
- **#1167** Busy-wait 99% CPU eliminated -- main loop now sleeps when no blocks are ready to spawn.
- **#1168** Daemon process now exits cleanly after all blocks complete (was hanging on orphaned threads).
- **#1169** Cascade invalidation no longer re-runs unrelated blocks -- BFS walk respects dependency boundaries.
- **#1170** JSON Schema and Pydantic validator now agree on allowed fields.
- **#1181** Fixed RE-PENDING duplicate execution during routing loops.
- **#1183** Per-block `timeout:` now actually applied to execution.
- **#1184** Per-block `model:` override now correctly reaches the provider call.
- **#1185** Block-level `save_as:` field now writes an alias of `result.json` under the custom filename; `{{ custom_name.json }}` placeholders resolve across all block output dirs.
- **#1190** Routing no longer races with `depends_on` scheduling -- when a gate routes to one branch, all non-chosen branches (and their exclusive descendants) are marked `skipped` so the main loop does not spawn them. Reconverging paths are preserved.

### Added

- **#1164** Daemon pidfile lock (`state/rein-daemon.pid`) with exclusive `fcntl.flock`. A second daemon instance exits immediately with a clear error instead of causing duplicate task execution. Lock is released on SIGTERM/SIGINT/normal exit.
- **#1186** Orchestrator decomposition: the monolithic `orchestrator.py` (2501 lines) was split into 9 focused modules:
  - `state_machine` -- dependency graph, cascade, routing direction, orphan/stuck detection
  - `block_resolver` -- flow control predicates, condition evaluation, `next:` resolution
  - `process_control` -- pause / resume / cancel semantics
  - `routing_engine` -- VERDICT signal parsing and routing rule matching
  - `error_handlers` -- `logic.error` and `on_error` script execution
  - `run_summary` -- metadata, summary, and task-status finalization
  - `prompt_assembler` -- template substitution with `task.input` and file placeholders
  - `config` (extended) -- validation and input handling
  - Internal `_apply_routing`, `_apply_next_state_machine`, `_reset_block_for_rerun`, `_invalidate_cascade` helpers
  
  `orchestrator.py` is now **1832 lines (-27%)**, with the remaining content tightly focused on threading and subprocess lifecycle.
- **#1187 / #1188 / #1189** Test suite expanded from 129 to ~390 tests (characterization, in-process integration, stable subprocess integration, and new unit tests). Coverage on `orchestrator.py` rose from ~14% to ~51%.

### Changed

- Flow Board v2: split CSS/JS files, zoom controls, fit-to-screen, phase ordering, loop sparkle behavior, edge labels.
- JSON Schema: `phase` limit raised from 10 to 1000.
- Documentation: README and `getting-started.md` expanded with Advanced Features reference (routing, error handling, phases, flow control, `save_as`, `readable_outputs`).

### Notes

- No breaking changes. Existing 3.3.0 workflows run unmodified.
- Known limitations (tracked for a future release): per-block budget limits (#1156), WebSocket full-state push (#1159), async wait blocks and sub-flow triggers (#1163).

## [3.3.0] - 2026-04-03

### Step Mode -- Run Workflows Incrementally

Rein can now execute workflows **one step at a time** instead of running everything in one blocking process. This is the major feature of v3.3.

**Before (v3.2):** `rein --flow my-flow` runs all blocks, blocks the terminal for minutes, and if it crashes halfway -- you restart from scratch.

**Now (v3.3):** `rein --step 1 --flow my-flow` runs one block, saves progress to SQLite, and exits. Run it again -- it picks up where it left off.

```bash
# First call: run 1 block
rein --flow product-eval --step 1 --input '{"product":"Rein"}'
# Exit code 2 = more steps remain

# Next calls: resume and run more blocks
rein --step 13 --task-dir /agents/tasks/task-20260402-170000
# Runs up to 13 blocks (parallel if dependencies allow)

# Run everything remaining
rein --step 0 --task-dir /agents/tasks/task-20260402-170000
# Exit code 0 = workflow complete
```

**Exit codes:** `0` = workflow complete, `2` = more steps remain, `1` = error.

**Why this matters:**
- Cron jobs can drive workflows: one block per tick, predictable resource usage
- Different agents can run different blocks (see Agent Routing below)
- Workflows can pause for hours/days between steps (human review, approvals)
- Crash recovery is automatic -- SQLite tracks which blocks are done

### Agent Routing -- Different Agents Per Block

Blocks can now specify **who** should run them with the `agent:` field:

```yaml
blocks:
  - name: draft
    agent: smm           # Only the SMM agent runs this block
    prompt: "Write a social media post..."
  - name: review
    agent: editor         # Only the editor agent runs this
    depends_on: [draft]
    prompt: "Review: {{ draft.json }}"
```

Use `--agent-id` to tell Rein which agent you are:

```bash
# SMM agent's cron job -- only runs "draft"
rein --step 1 --task-dir task-2000 --agent-id smm

# Editor's cron job -- only runs "review"
rein --step 1 --task-dir task-2000 --agent-id editor
```

Blocks without `agent:` run for anyone. Without `--agent-id`, all blocks run (backward compatible).

### Agent Config (agent.yaml)

Rein now reads `agent.yaml` from agent directories when a block has `agent:` field. This provides model overrides, security constraints, and OS user isolation.

```yaml
# /agents/smm/agent.yaml
name: smm
model: claude-sonnet-4-20250514    # Overrides flow-level model
linux_user: agent-smm              # Run logic scripts as this OS user
department: marketing
forbidden_behavior:
  - modify_other_agents
  - access_credentials
```

### Error Handlers

Two levels of error handling for workflow blocks:

```yaml
# Flow-level (catches any block failure)
on_error: scripts/notify-telegram.sh

blocks:
  - name: critical-step
    prompt: "..."
    logic:
      error: scripts/rollback.sh    # Block-level (specific handler)
```

Priority: `logic.error` (per-block) runs first. If it succeeds, `on_error` (global) is skipped. If `logic.error` fails, `on_error` runs as fallback. Handlers receive JSON context on stdin: `{block_name, error, task_dir, task_id, flow_name}`.

### Per-Run Structured Logs

Each block execution now creates a detailed log at `task_dir/{block}/runs/run-NNN.log`:

```
17:24:01.123 | BLOCK START | run=0 agent=smm phase=1
17:24:01.456 | PROMPT | chars=1847 preview="You are a social media..."
17:24:05.789 | LLM RESPONSE | chars=2341 duration=4.3s
17:24:06.012 | LOGIC.POST START | script=scripts/save-draft.sh
17:24:06.234 | LOGIC.POST OK | script=scripts/save-draft.sh
17:24:06.345 | BLOCK DONE | status=done saved=outputs/result.json
```

Revision loops create `run-001.log`, `run-002.log`, etc. -- full history of every attempt.

### Security Fixes

- Removed hardcoded internal IP addresses from source code
- Added path traversal protection (realpath containment checks)
- Task directory names validated against safe character set
- API keys scrubbed from log files (sk-*, anthropic-*, Bearer tokens)
- MCP server `agents_dir` pinned to environment variable (callers cannot override)

### Other Changes

- `run_count` now persists in SQLite across step invocations (existing databases auto-migrate)
- File lock prevents concurrent step invocations on the same task directory
- `summary.json` now includes per-block stats (runs, status, phase, duration)
- `linux_user` from agent config: logic scripts run as specified OS user via `sudo -u`
- 57 new tests (step mode, agent config, error handlers)

## [3.2.0] - 2026-02-20

### Added
- Declarative `inputs:` section in workflow YAML for pre-dispatch validation
- `InputFieldConfig` Pydantic model with `description`, `required`, `default` fields
- Cross-check validator: verifies `{{ task.input.X }}` placeholders match declared inputs
- Unresolved placeholder safety net in `assemble_prompt()`
- MCP `list_flows` now shows inputs schema per flow
- MCP `create_task` accepts `input_json` parameter
- Centralized logging module (`rein/log.py`) replacing print statements

### Changed
- Replaced all `print()` calls with structured `logging` in orchestrator and daemon
- Internal diagnostics go to stderr (`[REIN] LEVEL: message` format)
- CLI user output goes to stdout via separate console logger

## [3.1.3] - 2026-01-16

### Fixed
- Inverted `skip_if_previous_failed` logic -- blocks were skipped when flag was false

### Changed
- Increased LLM API timeout from 120s to 300s

## [3.1.2] - 2026-01-15

### Fixed
- Race condition between PHP UI and daemon writing to status.json
- PHP now reads block status from rein.db (SQLite) as single source of truth
- Restart properly clears rein.db state

## [3.1.1] - 2026-01-04

### Security
- Logic scripts now run in task directory (`cwd=task_dir`) instead of project root
- Default file access restricted to task directory only

### Added
- SECURITY.md documenting task isolation rules

## [3.1.0] - 2026-01-02

### Changed
- Renamed project from "Dog" to "Rein"
- Updated all internal references, log prefixes, temp directories, env variables

## [3.0.0] - 2026-01-02

### Added
- Block isolation architecture: each block gets `{inputs,outputs,logs}/` subdirectories
- Standard output naming: all blocks write to `result.json`
- UI columns: FLAGS (P/D/L/N/S/C/R) and IN/OUT data sizes
- Automatic task directory creation

### Removed
- Symlinks between blocks -- replaced with direct reads via `task_dir/dep/outputs/`

## [2.5.5] - 2026-01-02

### Added
- Input directory architecture: `inputs/<block>/` with symlinks to dependency outputs
- `input_dir` and `block_config` fields in logic script context

### Fixed
- `custom: true` (boolean) no longer causes `join()` type error

## [2.5.4] - 2026-01-01

### Added
- State machine flow control via `next` field (simple string or conditional list)
- `max_runs` for loop protection in revision loops
- Condition syntax: `{{ result.field }}`, comparisons, equality checks
- `--question FILE` for simple question input

### Fixed
- ClaudeWrapper file access with `--tools` and `--add-dir` flags

## [2.5.3] - 2026-01-01

### Added
- `skip_if_previous_failed` block parameter (default: false)
- `continue_if_failed` block parameter (default: true)
- Flow control logging for skipped blocks and workflow stops

## [2.5.2] - 2025-12-31

### Added
- Task execution mode with `--task` flag
- `task.yaml` configuration format
- Automatic status tracking: pending -> running -> completed/failed
- Memory system callbacks for result storage

## [2.5.1] - 2025-12-30

### Added
- Parallel block execution support

### Fixed
- Placeholder substitution with regex (preserves spaces)
- JSON extraction from mixed text responses
- Per-flow `.env` file loading

## [2.5.0] - 2025-12-28

### Added
- Flow-centric architecture with `flows/`, `specialists/`, `teams/` directories
- Logic phases: `pre`, `post`, `validate`, `custom`
- Per-flow `.env` configuration
- Specialist system with Markdown definitions and team tone injection
- `{{ file.json }}` placeholder substitution in prompts

## [2.4.0] - 2025-12-20

### Added
- Unix domain socket server for async command handling
- Pause/resume individual processes and entire workflow
- Process cancellation
- Interactive commands: `pause`, `resume`, `cancel`, `status`, `log`, `list`

## [2.3.0] - 2025-12-18

### Added
- SQLite database for process state persistence
- Resume from previous run with `--resume RUN_ID`
- State recovery on interruption

## [2.2.0] - 2025-12-15

### Added
- Block-level dependencies with `depends_on`
- Automatic phase calculation from dependency graph
- Semaphore-based parallelism control (`max_parallel`)
- Blocking pause support

## [2.1.0] - 2025-12-10

### Added
- Rich terminal UI (htop-like) with live process monitoring
- Progress bars, CPU/memory metrics, elapsed time
- Color-coded status display

## [2.0.0] - 2025-12-08

### Added
- Initial release as workflow orchestrator
- Process manager with dependency tracking
- YAML-based workflow configuration
- JSON output per block
- SQLite state persistence
- Unix domain socket command interface
