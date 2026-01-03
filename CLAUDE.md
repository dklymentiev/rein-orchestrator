# Instructions for Claude

**Project:** Rein - Workflow Orchestrator
**Status:** Production (Python 3.10+)
**Language:** English (documentation), Russian (conversation)

## Project Structure

```
/server/scripts/rein/
|-- rein.py             # Main orchestrator + htop-like UI (~2400 lines)
|-- rein-cli.sh         # CLI wrapper
|-- rein-cmd.sh         # Send commands to running workflows
|-- rein-workflows.sh   # List active workflows
|-- rein-status.sh      # Quick status
|-- rein-history.sh     # Run history
|-- rein-generator/     # Workflow generator (Claude API)
|-- models/             # Pydantic + JSON Schema validation
|-- schemas/            # JSON schemas for workflows/teams
|-- README.md           # User documentation
|-- MEMORY.md           # Project marker (guid: rein-001)
+-- CLAUDE.md           # This file
```

## Key Components

### rein.py

**Classes:**
- `Process` - Data class representing a managed block
- `ReinState` - SQLite state management
- `ProcessManager` - Semaphore + block spawning + monitoring
- `ReinUI` - Rich terminal UI (htop-like)

**Main flow:**
1. Load YAML workflow config
2. Validate with JSON Schema + Pydantic
3. Create ProcessManager with semaphore
4. Spawn blocks as processes
5. Monitor in background threads
6. Display htop-like UI with live updates

### Key Features

- Block isolation: each block gets own directory
- Dependency graph: blocks wait for dependencies
- State machine: conditional transitions (if/else/goto)
- Logic scripts: pre/post/validate/custom phases
- Visual monitoring: FLAGS and IN/OUT columns
- Runtime control: pause/resume/cancel via socket

## Testing

```bash
# Run a workflow
./rein.py --flow deliberation --input '{"topic": "test"}'

# Quick status
./rein-workflows.sh

# Send command
./rein-cmd.sh status
```

## Related Documents

- Version: 3.1.0
- See CHANGELOG.md for version history
- See README.md for full documentation
