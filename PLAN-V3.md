# Dog v3.0 Implementation Plan

## Overview

Upgrade from v2.5.5 to v3.0 with new block-isolated directory structure.

## Key Change

**Before (v2.5.5):**
```
task-xxx/
├── outputs/
│   ├── block1.json
│   └── block2.json
└── inputs/
    └── block2/
        └── block1.json -> ../outputs/block1.json
```

**After (v3.0):**
```
task-xxx/
├── input/                    # Workflow input
│   └── task.json
├── output/                   # Workflow output
│   └── result.json
│
├── block1/                   # Block directory
│   ├── inputs/               # Symlinks to dependencies
│   ├── outputs/
│   │   └── result.json
│   └── logs/
│       └── run.log
│
└── block2/
    ├── inputs/
    │   └── block1.json -> ../block1/outputs/result.json
    ├── outputs/
    │   └── result.json
    └── logs/
```

## Implementation Steps

### Phase 1: Setup

1. Copy current dog to dog-v2 (stable backup)
2. Create dog-v3 directory
3. Copy core files: dog.py, schemas/, models/

### Phase 2: Directory Structure

4. Modify `_prepare_input_dir()`:
   - Create `task/block/inputs/` instead of `task/inputs/block/`
   - Symlinks point to `../dep/outputs/result.json`

5. Modify `_get_output_dir()`:
   - Return `task/block/outputs/` instead of `task/outputs/`
   - Output file: `result.json` (not `block.json`)

6. Add `_create_block_dir(block_name)`:
   - Creates `task/block/{inputs,outputs,logs}/`

7. Add workflow-level I/O:
   - `task/input/task.json` - input parameters
   - `task/output/result.json` - final result (copy from last block)

### Phase 3: Logging

8. Per-block logs:
   - `task/block/logs/run.log` - stdout/stderr from logic scripts
   - `task/block/logs/claude.log` - Claude API request/response

### Phase 4: Testing

9. Test with arithmetic-test workflow (50 blocks)
10. Test with deliberation workflow (Claude API)

### Phase 5: Documentation

11. Update README.md
12. Update CHANGELOG.md
13. Create MIGRATION.md (v2 -> v3)

## Files to Modify

| File | Changes |
|------|---------|
| dog.py | `_prepare_input_dir`, `_get_output_dir`, `_create_block_dir` |
| VERSION | 3.0.0 |
| schemas/workflow-v3.0.0.json | New schema |
| models/workflow.py | Update paths |

## Backward Compatibility

- v2 workflows will NOT work in v3 (different output paths)
- Keep dog-v2 for existing workflows
- Migration script: convert v2 task outputs to v3 structure

## Future (v3.1+)

- Timestamped outputs: `outputs/result_run001.json`
- Retry logic: `retry: 3`
- Resource pools: `resource_pool: video`
- Notifications: `on_failure: notify`
- Heartbeat: `state/heartbeat`
- Checkpointing: `checkpoint/progress.json`

## Decision

- v3.0 = directory structure change only
- Production hardening = v3.1+
