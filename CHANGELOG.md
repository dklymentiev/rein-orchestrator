# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.3.0] - 2026-04-02

### Added
- **Async step mode** (`--step N`): execute up to N ready blocks per invocation, persist state to SQLite, exit. Enables cron-driven incremental workflow execution.
- **Agent routing** (`--agent-id NAME`): filter block execution by agent identity. Blocks with `agent:` field only run when matching agent calls. Blocks without `agent:` run for anyone.
- **Step resume** (`--step N --task-dir PATH`): resume workflow from existing task directory without specifying `--flow`. Flow name inferred from `input/task.json`.
- **File lock** (`state/rein.lock`): exclusive `fcntl.flock` prevents concurrent step invocations on the same task directory. Second caller exits cleanly (code 0).
- **`run_count` persistence**: `run_count` column added to SQLite `processes` table with automatic schema migration for existing databases. `max_runs` loop protection now works across step invocations.
- **Step exit codes**: 0 = workflow complete, 2 = more steps remain, 1 = error.
- **Comprehensive test suite** (`tests/test_step_mode.py`): 37 tests covering functional, integration, infrastructure, e2e, run_count persistence, file locking, and agent routing.

### Changed
- `ProcessManager.run_step()` is a new public method (separate from `run_workflow()`) with bounded execution lifecycle, no UI, no signal handlers.
- `_initialize_all_processes()` now restores `run_counts` from SQLite on resume.
- Stuck detection improved: step mode exits when no blocks can be spawned (agent filter, deps blocked) instead of looping indefinitely.

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
