# Memory

guid: agent-pm2-dog-001
created: 2025-12-30
updated: 2025-12-31

Project memory marker for Agent-PM2 ("Dog") - Multi-Agent Specialist Orchestrator.

## PHASE 2.5: SPECIALIST ARCHITECTURE FOCUS

**MAIN CONCEPT:** Transform Dog from shell-command executor → specialist-driven orchestrator

**4-Layer Architecture:**
1. **Specialists** (MD files) - Reusable AI agent instructions
2. **Teams** (YAML) - Groups of specialists + shared tone
3. **Workflows** (YAML) - Process logic, stages, dependencies, data flow
4. **Dog** (Python) - Orchestrator that executes everything

**Read First:**
- **PHASE_2_5_PLAN.md** ← START HERE (this file explains everything)
- **SPECIALIST_ARCHITECTURE.md** (full architecture details)

**Key Structure:**
```
agents/
├── specialists/     (50+ MD files - agent definitions)
│   ├── poet-specialist.md
│   ├── critic-specialist.md
│   └── ... more
├── teams/          (YAML - agent groups + tone)
│   ├── team-poetry.yaml
│   └── ... more
└── workflows/      (YAML - process definitions)
    ├── create-poem.yaml
    └── ... more
```

---

## Project Status

**Phase:** MVP v1.0 (archived) → Phase 2.5 (Specialist Architecture - Ready)
**Status:** dog-v2.py ready (copy of v1), Phase 2.5 plan defined
**Architecture:** Multi-Agent Specialist System (Specialists → Teams → Workflows → Dog)

## Key Decisions

1. **Language:** Python for MVP (quick iteration) → Go for production
2. **UI:** Rich library for htop-like terminal interface
3. **State:** SQLite for persistent tracking
4. **Execution:** Threading with Semaphore for process control

## Implementation Details

- Main file: `dog.py` (single file, easy to understand)
- Config format: YAML with blocks
- Process monitoring: psutil for CPU/MEM metrics
- Real-time UI: Rich library with live tables

## Features Roadmap

See `FEATURES_ROADMAP.md` for complete feature list (7 tiers):

**Tier 1 (Next):** Error handling, result verification, recovery policies
**Tier 2:** Process/workflow pause/resume, priority, interactive CLI
**Tier 3:** Conditional execution, templates, environment/secrets
**Tier 4:** Monitoring, observability, health checks, UI enhancements
**Tier 5:** Containers, plugins, API, multi-machine, git integration

**Estimated:** 420 dev hours total (170 for production-ready)

See `CHECKLIST.md` for detailed implementation tasks for Tier 1.

## Phase 2.5: Multi-Agent Specialist System

**Status:** Clean rewrite ready (2025-12-31)

### Architecture
```
Specialists (MD files) + Teams (YAML tone) + Workflows (YAML logic) → Dog (Claude API orchestrator)
```

### What Was Done Today
1. ✓ Archived old Dog v1.0 (shell execution model)
2. ✓ Created clean `/agents/` directory structure
3. ✓ Documented readiness analysis (40% ready, 60% rewrite needed)
4. ✓ Prepared 3 key documents:
   - SPECIALIST_ARCHITECTURE.md (design)
   - ARCHITECTURE_ITERATION.md (readiness)
   - IMPLEMENTATION_READY.md (next steps)
5. ✓ Created agents/{specialists, teams, workflows} directories with READMEs

### What Requires Rewrite
- dog.py: Complete rewrite for Claude API (2-3 days)
- Remove command execution
- Add specialist loading + team tone + prompt assembly

### What Stays the Same
- Semaphore logic (parallelism)
- Dependency resolution (depends_on)
- SQLite state management
- Logging structure
- dog-cli.sh, dog-status.sh, dog-history.sh tools

### Next Implementation (Phase 2.5)
Day 1: Rewrite dog.py with DogEngine class
Day 2: Create 10 specialist examples
Day 3: Create team examples
Day 4: Create workflow examples
Day 5: Test end-to-end

**Effort:** 4-5 days
**Clean slate:** Yes (no legacy constraints)

### Implementation Started (2025-12-31)

**Version Strategy: Incremental Development**
- dog-v1-archive/: Old code (archived)
- dog-v2.py: New implementation (in development, 8.7KB)
- dog.py: Final (to be created from v2 after testing)

**File Structure Ready:**
```
/server/scripts/agent-pm2-dog/
├── dog-v2.py           [NEW - 8.7KB]
├── dog-cli.sh          [KEEP]
├── dog-status.sh       [KEEP]
├── dog-history.sh      [KEEP]
├── dog-v1-archive/     [ARCHIVED]
├── agents/             [NEW]
│   ├── specialists/    [ready for population]
│   ├── teams/         [ready for population]
│   └── workflows/     [ready for population]
└── Documentation/
    ├── SPECIALIST_ARCHITECTURE.md
    ├── ARCHITECTURE_ITERATION.md
    ├── IMPLEMENTATION_READY.md
    └── VERSION_STRATEGY.md
```

**dog-v2.py Status:**
- DogEngine class: defined
- load_workflow(), load_team(), load_specialist(): ✓
- assemble_prompt(), call_claude(), run_block(): ✓
- execute_workflow(), CLI main(): ✓
- Needs: error handling, SQLite, semaphore, full logging

**Next: Development Phase 2.5-A (enhance dog-v2.py)**
