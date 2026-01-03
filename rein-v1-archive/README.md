# Dog v1 Archive - MVP Implementation

**Date Archived:** 2025-12-31
**Version:** MVP v1.0 (Tier 1)
**Status:** Archived for clean rewrite

## What's Here

Old Dog implementation (Python MVP):
- `dog.py` - Main orchestrator (shell command execution)
- `agent.py` - Mock agent implementation
- `mock_agent.py` - Test agent
- `test-*.yaml` - Test workflow files
- `search-*.yaml` - Example workflows
- `*.log` - Old log files

## Why Archived

Clean rewrite for Multi-Agent Specialist Architecture:
- Old: Shell command execution
- New: Claude API calls with specialist agents
- New: Team tone + prompt assembly + data flow

## Key Learnings from v1

✓ Semaphore-based parallelism works well
✓ SQLite state management is solid
✓ Logging structure (dog.log, dog.db) is good
✓ Dependency resolution (_calculate_phase) is correct
✓ Basic YAML config approach is sound

✗ Shell execution model incompatible with Claude API
✗ Command-based blocks don't support agent composition
✗ No data flow between blocks
✗ No specialist/team concept

## For Reference

See SPECIALIST_ARCHITECTURE.md for new approach.

If you need anything from v1:
- Copy from this archive
- Reference implementation details
- Learning: what works, what doesn't
