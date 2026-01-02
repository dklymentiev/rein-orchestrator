# Dog v2 Changelog

## [2.5.4] - 2026-01-01

### Added - State Machine Flow Control (`next` field)

**Major Feature: Conditional transitions and revision loops**

New block-level fields for state machine style flow:

- `next` - Specify next block to execute after completion
  - Simple string: `next: "publish"` - always go to publish
  - Conditional list with `if`/`else`:
    ```yaml
    next:
      - if: "{{ result.approved }}"
        goto: publish
      - else:
        goto: revision
    ```

- `max_runs` (default: 1) - Maximum times a block can run (loop protection)

### Condition Syntax

Conditions support `{{ result.field }}` placeholders with comparison operators:

- Truthy check: `{{ result.approved }}`
- Equality: `{{ result.status == 'approved' }}`
- Comparison: `{{ result.score > 0.8 }}`

### Usage Example: Approval Loop

```yaml
blocks:
  - name: writer
    specialist: content-writer
    prompt: "Write article about {{ task.input.topic }}"
    next: censor

  - name: censor
    specialist: content-censor
    prompt: "Review article from {{ writer.json }}"
    next:
      - if: "{{ result.approved }}"
        goto: publish
      - else:
        goto: revision

  - name: revision
    specialist: content-editor
    prompt: "Revise based on feedback: {{ censor.json }}"
    max_runs: 2
    next: censor

  - name: publish
    specialist: publisher
    prompt: "Publish final article"
```

### Implementation Details

New fields in Process dataclass:
- `next_spec` - stores next block specification
- `max_runs` - maximum run count
- `run_count` - current run count

New structures in ProcessManager:
- `next_queue` - queue of blocks triggered by `next`
- `run_counts` - tracks how many times each block has run
- `block_configs` - stores block configs for re-running

New methods:
- `_evaluate_next_block()` - evaluates `next` spec and returns target block
- `_evaluate_condition()` - parses and evaluates `{{ }}` conditions
- `_resolve_path()` - resolves dot paths like `result.approved`

### Other Additions
- `--question FILE` - Simple question file support (no task directory needed)
- Auto-detect `context/` subdirectory for file access
- Questions directory: `/server/agents/questions/`

### Fixed
- ClaudeWrapper file access: added `--tools` and `--add-dir` CLI flags
- run-specialist.py: auto-extracts directories from task.md paths

## [2.5.3] - 2026-01-01

### Added - Flow Control Parameters

**New Block-Level Control Parameters for Resilient Workflows:**

- `skip_if_previous_failed` (default: false) - Block execution control
  - If true: Execute block even if previous blocks failed
  - If false: Skip block if any previous block failed

- `continue_if_failed` (default: true) - Workflow continuation control
  - If true: Workflow continues even if this block fails (optional block)
  - If false: Workflow stops immediately on block failure (critical block)

### Implementation Details

New methods added to ProcessManager:

1. `_get_previous_blocks_status()` - Returns list of failed block names
2. `_should_execute_block()` - Determines if block should execute based on `skip_if_previous_failed`
3. `_should_continue_after_failure()` - Determines if workflow should continue based on `continue_if_failed`

New flow control flags in ProcessManager:

- `stop_workflow` - Set to True when critical failure occurs
- `stop_reason` - Human-readable reason for workflow stop

### Usage Example

```yaml
blocks:
  - name: data_validation
    specialist: validator
    continue_if_failed: false  # CRITICAL - stop if validation fails

  - name: data_enrichment
    specialist: enricher
    skip_if_previous_failed: false  # Skip if validation failed
    continue_if_failed: true  # Continue even if enrichment fails

  - name: backup_operation
    specialist: backup
    skip_if_previous_failed: true  # Always try backup, even if earlier blocks failed
    continue_if_failed: true  # Don't stop workflow if backup fails

  - name: final_report
    specialist: reporter
    skip_if_previous_failed: false  # Skip if any dependency failed
    continue_if_failed: false  # Stop if report generation fails
```

### Default Behavior

- All blocks are `continue_if_failed: true` (optional) by default
- All blocks are `skip_if_previous_failed: false` by default (require success)
- This ensures safe workflows: failures in earlier stages prevent dependent stages from running

### Logging

New log entries for flow control:

- `BLOCK SKIPPED | {name} | skip_if_previous_failed=false and failures detected`
- `WORKFLOW STOPPED | {name} | continue_if_failed=false`

---

## [2.5.2] - 2025-12-31

### Added - Task System Integration

- Task execution mode with `--task` flag
- task.yaml configuration format
- status.json automatic status tracking
- Memory system callbacks for result storage
- Task output directory organization

### Features

- Separate flows/ (templates) and tasks/ (executions) directories
- Automatic status updates: pending → running → completed/failed
- JSON result file collection in outputs/ directory
- Optional memory system integration

---

## [2.5.1] - 2025-12-30

### Added - Russian Language Support & Complex Workflows

- Russian-language specialist templates
- Parallel block execution (creation_1, creation_2, creation_3 simultaneous)
- Russian humor poetry workflow example
- Proper JSON data flow between parallel stages

### Fixed

- Placeholder substitution with regex matching (preserves spaces)
- JSON extraction from mixed text responses
- Logic script envelope unwrapping
- Per-flow .env file loading with OpenRouter API support

---

## [2.5.0] - 2025-12-28

### Major Addition - Flow-Centric Architecture

**New directory structure:**

```
agents/
├── flows/              # Flow templates
│   ├── create-poem/
│   │   ├── create-poem.yaml
│   │   ├── .env
│   │   └── logic/
│   │       ├── validate-themes.py
│   │       ├── enhance-draft.py
│   │       └── validate-revision.py
│   └── russian-humor-poetry/
│       ├── russian-humor-poetry.yaml
│       ├── .env
│       └── logic/
├── specialists/        # Specialist instructions
│   ├── poet.md
│   ├── critic.md
│   └── poet-humor-ru.md
└── teams/             # Team configurations
    ├── team-creative.yaml
    └── team-russian-humor.yaml
```

### New Features

1. **Logic Phases**
   - pre: Run before Claude (data preparation)
   - post: Run after Claude (result processing)
   - validate: Validation logic (quality checks)
   - custom: Skip Claude entirely

2. **Per-Flow Configuration**
   - .env files in flow directories
   - OpenRouter API support with fallback to Anthropic

3. **Specialist System**
   - Load instructions from .md files
   - Team tone injection
   - Prompt assembly from components

4. **Placeholder Substitution**
   - `{{ file.json }}` placeholders in prompts
   - Automatic file loading and JSON substitution
   - Handles both plain JSON and envelope-wrapped results

### Key Methods

- `load_team()` - Load team tone configuration
- `load_specialist()` - Load specialist instructions from .md
- `assemble_prompt()` - Build full prompt from components
- `call_claude()` - Unified API call (Anthropic or OpenRouter)
- `_run_logic()` - Execute logic scripts (Python or Shell)
- `_load_env_file()` - Load per-flow .env configuration

---

## [2.4.0] - 2025-12-20

### Added - Process Management Features

- Socket server for async command handling
- Pause/Resume individual processes
- Pause/Resume entire workflow
- Process cancellation
- Status queries via socket interface

### Commands

- `pause <uid|name>` - Pause specific process
- `resume <uid|name>` - Resume paused process
- `cancel <uid|name>` - Cancel process permanently
- `pause-workflow` - Pause entire workflow
- `resume-workflow` - Resume workflow
- `status` - Get workflow status
- `log <uid|name>` - Get process log info
- `list` - List all processes with UIDs

---

## [2.3.0] - 2025-12-18

### Added - Database Persistence

- SQLite database for process state
- Resume from previous run with `--resume RUN_ID`
- State recovery on interruption
- Persistent process tracking across sessions

### Features

- Automatic database creation
- State serialization on each process update
- Fresh run mode vs. resume mode
- Log directory organization by run_id

---

## [2.2.0] - 2025-12-15

### Added - Dependency Management

- Block-level dependencies with `depends_on` list
- Automatic phase calculation
- Semaphore-based parallelism control
- Blocking pause support (`blocking_pause` flag)

### Features

- Phases calculated from dependency graph
- Parallel execution within same phase
- Configurable max_parallel (default: 3)
- Wait for all dependencies before spawning block

---

## [2.1.0] - 2025-12-10

### Added - Rich UI Monitoring

- htop-like terminal interface using Rich library
- Live process table with real-time updates
- Progress bars for each process
- Overall workflow progress tracking
- CPU and memory metrics
- Time elapsed display with timeout countdown

### Features

- Color-coded status display
- Process UIDs for identification
- Agent name display
- Workflow pause indicator

---

## [2.0.0] - 2025-12-08

### Initial Release - Agent Process Manager

**Architecture:** Dog v2 - Meta-orchestrator for workflows

- Process manager with dependency tracking
- Configuration via YAML
- JSON output files for each block
- htop-like UI for monitoring
- SQLite database for state
- Socket server for async commands

**Key Concepts:**

- Blocks: Smallest unit of work
- Phases: Automatic ordering based on dependencies
- Workflow: Complete execution graph
- Semaphore: Parallel execution control

**Status Codes:**
- waiting: Pending dependencies
- running: Currently executing
- done: Completed successfully
- failed: Execution error
- paused: Temporarily halted
- cancelled: Permanently cancelled

---

## Version History Notes

- **v2.5.3**: Flow control parameters for resilient workflows
- **v2.5.2**: Task system with memory integration
- **v2.5.1**: Russian language support
- **v2.5.0**: Flow-centric architecture with specialists
- **v2.4.0**: Advanced process management (pause/resume)
- **v2.3.0**: Database persistence and resume capability
- **v2.2.0**: Dependency management and phases
- **v2.1.0**: Rich UI with real-time monitoring
- **v2.0.0**: Initial Dog v2 release

## Next Planned Releases

### v2.6.0
- Webhook support for external triggers
- Conditional blocks based on previous output
- Multi-agent consensus mechanism

### v2.7.0
- RAG integration with knowledge bases
- Dynamic block generation based on data
- Distributed execution across multiple nodes

### v3.0.0
- Message queue backend (RabbitMQ/Redis)
- Advanced retry mechanisms with exponential backoff
- Metrics collection and dashboards
