# Dog Architecture Iteration - Multi-Agent System Analysis

**Date:** 2025-12-31
**Type:** Architecture Decision & Readiness Assessment
**Status:** Approved for Clean Rewrite
**GUID:** agent-pm2-dog-001

## Problem Statement

How to coordinate 50+ specialist agents in complex workflows using Dog?

## Solution Proposed

4-layer architecture:
1. **Specialists** (MD files - agent instructions)
2. **Teams** (YAML - combine agents + set tone)
3. **Workflows** (YAML - define process logic)
4. **Dog** (orchestrator - agnostic execution)

## Readiness Assessment

### Component: Ready for Reuse (100%)

| Component | Status | Notes |
|-----------|--------|-------|
| Semaphore (parallelism) | ✓ Ready | `threading.Semaphore(max_parallel)` works perfectly |
| Dependencies | ✓ Ready | `depends_on` logic in `_calculate_phase()` |
| SQLite state | ✓ Ready | `DogState` class manages process state |
| Logging | ✓ Ready | dog.log, dog.db, summary.json, metadata.json |
| Directory structure | ✓ Ready | /tmp/dog-runs/run-* already in place |

### Components: Require Clean Rewrite (60%)

| Component | Current | Needed | Action |
|-----------|---------|--------|--------|
| Execution model | `subprocess.Popen()` shell commands | Claude API calls | **Rewrite** |
| YAML structure | `blocks[].command` | `blocks[].agents`, `blocks[].prompt`, `blocks[].input_from`, `blocks[].save_as` | **Redesign** |
| Process handling | Shell exit codes | API response parsing + file saving | **Rewrite** |
| Prompt assembly | None (commands are direct) | Team tone + specialist instructions + prompt + data substitution | **Create new** |
| File I/O | stdout/stderr capture | Result JSON files (save_as) | **Expand** |

### Components: New Functionality Needed

| Feature | Implementation |
|---------|-----------------|
| Specialist loading | `load_specialists(agent_names) -> Dict[name, instructions]` |
| Team loading | `load_team_tone() -> str` |
| Data substitution | `substitute_data(prompt, input_files) -> str` |
| Claude API integration | `call_claude(prompt) -> str` with Anthropic SDK |
| Prompt assembly | `assemble_prompt(block, team_tone, specialists) -> str` |

## Decision: Clean Rewrite

**Rationale:**
- No need for backward compatibility
- Legacy command execution model fundamentally different from Claude API model
- Cleaner to rewrite than to refactor
- Can reuse infrastructure (logging, state, dependency logic)

**Approach:**
1. Archive current Dog (all old code)
2. Create clean directory structure
3. Write new dog.py from scratch
4. New implementation: ~500 lines (vs 1000+ old)

## Implementation Plan

### Phase 1: Infrastructure (Today)
- Create `/server/agents/` directory structure
- Archive current Dog to `_archive/dog-v1-mvp/`
- Move all test YAML files to archive

### Phase 2: New Dog Engine (Days 1-2)
- Write `dog.py` with DogEngine class
- Methods:
  - `load_workflow(yaml_file)`
  - `load_team_tone(team_name)`
  - `load_specialists(agent_names)`
  - `assemble_prompt(block, team_tone, specialists)`
  - `call_claude(prompt)`
  - `substitute_data(prompt, input_files)`
  - `run_block(block, dependencies_state)`
  - `execute_workflow()`

### Phase 3: Core Specialists (Day 3)
Create 10 example specialists:
- poet-specialist.md
- critic-specialist.md
- analyst.md
- developer.md
- security-expert.md
- tester.md
- designer.md
- pm-specialist.md
- qa-specialist.md
- integrator.md

### Phase 4: Teams & Workflows (Days 4-5)
Create example teams:
- team-poetry.yaml
- team-code-review.yaml
- team-security.yaml
- team-content.yaml

Create example workflows:
- create-poem.yaml
- review-code.yaml
- security-audit.yaml

## Effort Estimate

| Task | Duration | Notes |
|------|----------|-------|
| Archive & setup | 1 hour | Moving files, creating dirs |
| dog.py rewrite | 2-3 days | ~500 lines, core logic |
| Specialists (10) | 1 day | Creating example instructions |
| Teams (4-5) | 1/2 day | YAML configs |
| Workflows (3-5) | 1/2 day | Example processes |
| Testing | 1 day | Full workflow tests |
| **Total** | **4-5 days** | |

## Files to Archive

```
/server/scripts/agent-pm2-dog/
├── dog.py (old)
├── agent.py (old)
├── mock_agent.py
├── example.yaml
├── test-*.yaml
├── search-*.yaml
├── interactive-workflow.yaml
├── *.log files
└── dog-v1-archive/  ← Archive everything here
    └── README.md (what was archived when)
```

## New Directory Structure

```
/server/agents/
├── README.md          # Guide to multi-agent system
├── specialists/       # 50+ agent definitions
│   ├── poet-specialist.md
│   ├── critic-specialist.md
│   └── ... (48 more)
├── teams/            # Team configurations
│   ├── team-poetry.yaml
│   ├── team-code-review.yaml
│   └── ... (3-10 more)
└── workflows/        # Workflow definitions
    ├── create-poem.yaml
    ├── review-code.yaml
    └── ... (N workflows)

/server/scripts/agent-pm2-dog/
├── dog.py           # NEW - Multi-agent orchestrator
├── dog-cli.sh       # KEEP - Production tools
├── dog-status.sh    # KEEP - Production tools
├── dog-history.sh   # KEEP - Production tools
├── PRODUCTION_GUIDE.md  # KEEP
├── SPECIALIST_ARCHITECTURE.md  # KEEP
├── POETRY_EXAMPLE.md  # KEEP - for reference
└── dog-v1-archive/  # Archive of old code
    ├── dog-v1.py
    ├── agent.py
    ├── test-*.yaml
    └── README-ARCHIVE.md
```

## Key Principles for New Implementation

1. **Specialists are reusable**: One specialist used in many workflows
2. **Teams set tone**: Same team works together with consistent voice
3. **Data flows** between blocks: Results available for next stages
4. **Claude is stateless**: Each call includes full context
5. **Logging is complete**: Track all Claude calls, prompts, results
6. **YAML is declarative**: Logic in YAML, execution in Dog

## Success Criteria

✓ Can define workflow in YAML with agents, prompts, dependencies
✓ Can load specialists from MD files
✓ Can substitute data from previous blocks into prompts
✓ Can call Claude API with complete context
✓ Can run multi-stage workflows with parallelism
✓ Can log all results to dog.log, dog.db, summary.json
✓ Can check status with dog-cli.sh

## Next Steps

1. Archive current Dog → `/server/scripts/agent-pm2-dog/dog-v1-archive/`
2. Create `/server/agents/` structure
3. Begin Phase 2: Write new dog.py from scratch
4. Create first batch of specialists
5. Test with simple poem workflow
6. Iterate to complex workflows

---

**Decision Made:** Clean rewrite approved. Start with infrastructure setup tomorrow.
