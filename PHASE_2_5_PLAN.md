# Phase 2.5: Specialist Architecture Implementation

**Date:** 2025-12-31
**Status:** Ready to implement
**GUID:** agent-pm2-dog-001

## What is Phase 2.5?

Transform Dog v1 (shell-based process manager) into Dog v2 (specialist-driven orchestrator).

**Key shift:** From "run shell commands" → "orchestrate reusable specialist agents"

---

## Core Concept: 4-Layer Architecture

See **SPECIALIST_ARCHITECTURE.md** for full details.

### Layer 1: Specialists (MD files)
Reusable AI agent instructions, stored as Markdown.

```
agents/specialists/
├── poet-specialist.md
├── critic-specialist.md
├── analyst.md
├── developer.md
├── tester.md
└── ... (50+ more)
```

Each file = one specialist with role, expertise, constraints.

### Layer 2: Teams (YAML)
Group specialists with shared team tone.

```
agents/teams/
├── team-poetry.yaml
├── team-code-review.yaml
├── team-security-audit.yaml
└── team-creative.yaml
```

Example:
```yaml
name: team-poetry
tone: "You are part of a collaborative poetry team..."
agents:
  - poet-specialist
  - critic-specialist
```

### Layer 3: Workflows (YAML)
Define the process - stages, dependencies, data flow.

```
agents/workflows/
├── create-poem.yaml
├── review-code.yaml
├── security-audit.yaml
└── [any-process].yaml
```

Example:
```yaml
name: create-poem
team: team-poetry

blocks:
  - stage: ideation
    agents: [creative-1, creative-2]
    prompt: "Brainstorm poem themes..."
    parallel: true
    save_as: ideation.json

  - stage: draft
    agents: [poet-specialist]
    prompt: |
      Based on ideas:
      {{ ideation.json }}

      Write 4 lines of poetry...
    depends_on: ideation
    save_as: draft.json

  - stage: review
    agents: [critic-specialist]
    prompt: "Review this draft: {{ draft.json }}"
    depends_on: draft
    save_as: review.json

  - stage: finalize
    agents: [poet-specialist]
    prompt: |
      Original: {{ draft.json }}
      Feedback: {{ review.json }}
      Revise incorporating feedback...
    depends_on: review
    save_as: final.json
```

### Layer 4: Dog Orchestrator
Engine that executes everything:

1. Load workflow YAML
2. Load team YAML → get tone
3. For each block:
   - Load specialist instructions (MD)
   - Assemble prompt: tone + specialist + block_prompt + data
   - Execute block (call API or run command)
   - Save result
   - Track dependencies and parallelism
4. Log everything, manage state

---

## Implementation: 4 Phases

### Phase 2.5-A: Foundation (Week 1)
**Goal:** Dog v2 with specialist support

Current status:
- dog-v2.py = copy of dog-v1.py (working, has threading, SQLite, semaphore)
- agents/ directory structure ready
- SPECIALIST_ARCHITECTURE.md documented

What to do:
1. Modify dog-v2.py to load specialist MD files
2. Modify dog-v2.py to load team YAML (get tone)
3. Modify dog-v2.py to assemble prompts: tone + specialist + prompt + data
4. Test with simple 3-block workflow

**Output:** dog-v2.py can orchestrate specialists + teams + workflows

### Phase 2.5-B: Examples (Week 1, parallel)
**Goal:** 10 working examples

Create in agents/specialists/:
- poet-specialist.md
- critic-specialist.md
- analyst.md
- developer.md
- security-expert.md
- tester.md
- debugger.md
- architect.md
- documenter.md
- integrator.md

Create in agents/teams/:
- team-poetry.yaml
- team-code-review.yaml
- team-security-audit.yaml

Create in agents/workflows/:
- create-poem.yaml
- review-code.yaml
- security-audit.yaml

**Output:** 10 ready-to-run example workflows

### Phase 2.5-C: Testing (Week 1, final)
**Goal:** Verify it works end-to-end

1. Test create-poem.yaml with real Claude API
2. Test review-code.yaml
3. Test parallel execution
4. Test dependencies
5. Verify logging works

**Output:** All workflows execute correctly

### Phase 2.5-D: Promote (Week 1, final)
**Goal:** Move v2 to production

1. Rename dog-v2.py → dog.py
2. Update dog-cli.sh to use new dog.py
3. Archive dog-v1-archive/ (keep for reference)
4. Document in QUICKSTART.md

**Output:** dog.py is production version

---

## Key Files

| File | Purpose | Status |
|------|---------|--------|
| dog-v2.py | Main orchestrator | Ready (copy of v1) |
| agents/specialists/*.md | Agent definitions | To create |
| agents/teams/*.yaml | Team configs | To create |
| agents/workflows/*.yaml | Workflow definitions | To create |
| SPECIALIST_ARCHITECTURE.md | Full architecture | Done |
| PHASE_2_5_PLAN.md | This file | Done |
| QUICKSTART.md | How to use | Exists |

---

## What Makes This Different from v1?

**Dog v1 (Shell-based):**
```yaml
blocks:
  - name: task-1
    command: "python3 agent.py --input data.txt"
  - name: task-2
    command: "python3 agent.py --mode review"
    depends_on: [task-1]
```
- Hard to reuse agents
- Commands duplicated across workflows
- No team collaboration model
- No specialist expertise capture

**Dog v2 (Specialist-based):**
```yaml
team: team-poetry

blocks:
  - stage: ideation
    agents: [creative-1, creative-2]
    prompt: "Brainstorm themes..."
    parallel: true

  - stage: draft
    agents: [poet-specialist]
    prompt: "Write based on: {{ ideation.json }}"
    depends_on: ideation
```
- Specialists defined once, used everywhere (DRY)
- Prompts are reusable across workflows
- Team tone sets collaboration model
- Specialist expertise captured in MD files
- **Dog is agnostic** - can call any API, service, or command via prompts

---

## Technical Details: How It Works

### Prompt Assembly

For each block, Dog builds a prompt:

```
[TEAM TONE]

---

[SPECIALIST 1 INSTRUCTIONS]

---

[SPECIALIST 2 INSTRUCTIONS]

---

[BLOCK PROMPT with substituted data]
```

Example:

```
You are part of a collaborative poetry team.
Work respectfully with your teammates...

---

# Poet Specialist

You are a professional poet with expertise in:
- Russian classical poetry
- Rhyme schemes and meter
- Emotional resonance

---

# Critic Specialist

You are an experienced poetry critic...

---

Based on these brainstorm ideas:
{
  "themes": [
    {"title": "Love", "description": "..."},
    ...
  ]
}

Write 4 lines of poetry that follow proper meter...
```

### Data Flow

Results stored as JSON, referenced in next block:

```yaml
blocks:
  - stage: ideation
    save_as: ideation.json
    # Produces: { "themes": [...] }

  - stage: draft
    prompt: |
      Based on: {{ ideation.json }}
      Write poem...
    save_as: draft.json
    # Produces: { "lines": [...] }

  - stage: review
    prompt: |
      Review: {{ draft.json }}
      Provide feedback...
    save_as: review.json

  - stage: finalize
    prompt: |
      Original: {{ draft.json }}
      Feedback: {{ review.json }}
      Revise...
    save_as: final.json
```

---

## Why This Architecture?

### DRY Principle
Define each specialist once:
```
poet-specialist.md → used in 5 workflows, 3 teams
tester.md → used in code-review, security-audit, qa
```

### Reusability
Mix and match specialists freely:
```yaml
# create-poem.yaml
agents: [poet-specialist, critic-specialist]

# security-audit.yaml
agents: [security-expert, tester, documenter]

# code-review.yaml
agents: [developer, tester, integrator]
```

### Transparency
See exactly what each specialist does:
- Open agents/specialists/poet-specialist.md
- Modify once, affects all workflows
- Easy to audit and improve

### Flexibility
Prompts can instruct anything:
- Call external APIs
- Run shell commands
- Generate code
- Interact with databases
- Anything Claude can understand

---

## Success Criteria

### Phase 2.5-A Complete When:
- [ ] dog-v2.py loads specialist MD files
- [ ] dog-v2.py loads team YAML and gets tone
- [ ] dog-v2.py assembles correct prompts
- [ ] Simple 3-block test workflow runs successfully

### Phase 2.5-B Complete When:
- [ ] 10 specialist MD files created and documented
- [ ] 3 team YAML files created
- [ ] 3 workflow YAML files created
- [ ] All examples tested and working

### Phase 2.5-C Complete When:
- [ ] create-poem.yaml passes end-to-end test
- [ ] review-code.yaml passes test
- [ ] Parallel execution verified
- [ ] Dependencies verified
- [ ] Logging verified

### Phase 2.5-D Complete When:
- [ ] dog-v2.py renamed to dog.py
- [ ] dog-cli.sh updated and tested
- [ ] QUICKSTART.md updated
- [ ] dog.py is production ready

---

## Key Links

- **SPECIALIST_ARCHITECTURE.md** - Full architecture design (start here!)
- **QUICKSTART.md** - How to run Dog
- **PRODUCTION_GUIDE.md** - Operations
- **ARCHITECTURE_COMPARISON.md** - Why Dog > Giselle for this use case

---

## Next Step

1. Read SPECIALIST_ARCHITECTURE.md carefully
2. Start Phase 2.5-A: modify dog-v2.py to load MD/YAML files
3. Create first specialist example (poet-specialist.md)
4. Test with create-poem.yaml workflow

Ready to begin!
