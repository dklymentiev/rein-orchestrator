# Multi-Agent Specialist Architecture for Dog

**Version:** Phase 2.5 Proposal
**Date:** 2025-12-31
**Status:** RFC (Request For Comments) - Ready for Discussion
**GUID:** agent-pm2-dog-001

## Core Vision

Build any process of any complexity using:
- **50+ specialist agents** (reusable MD files)
- **Team configurations** (YAML - agents + tone)
- **Workflow definitions** (YAML - logic, stages, dependencies)
- **Dog orchestrator** (agnostic, runs it all)

## The Problem It Solves

**Current state:**
- Dog executes commands in sequence
- Each command is isolated
- How to coordinate 50 different specialists?
- How to reuse agents across workflows?
- How to quickly modify processes?

**Solution:**
- Define agents once (specialists/*.md)
- Combine them into teams (teams/*.yaml)
- Build workflows with them (workflows/*.yaml)
- Dog orchestrates everything

## Architecture - Four Layers

### Layer 1: Specialists (MD Files)

Define each specialist once with their expertise, role, constraints.

```
/server/agents/specialists/
├── poet-specialist.md
├── critic-specialist.md
├── analyst.md
├── developer.md
├── security-expert.md
├── tester.md
└── ... × 50
```

**Example: poet-specialist.md**
```markdown
# Poet Specialist

You are a professional poet with expertise in:
- Russian classical and modern poetry
- Rhyme schemes and meter analysis
- Emotional resonance and imagery
- Semantic correctness

Your role: Write poetic lines with deep meaning and proper rhythm.

When given a theme and context:
1. Understand the emotional tone and requirements
2. Create lines with natural, flowing rhythm
3. Ensure semantic correctness
4. Make the result memorable and impactful

Always preserve the author's intent while improving execution.
```

### Layer 2: Teams (YAML with Tone)

Combine specialists into teams, set working tone.

```
/server/agents/teams/
├── team-poetry.yaml
├── team-code-review.yaml
├── team-security-audit.yaml
└── team-creative.yaml
```

**Example: team-poetry.yaml**
```yaml
name: team-poetry
description: "Collaborative poetry team"

# This tone is prepended to every agent's instructions
tone: |
  You are part of a collaborative poetry team.
  Your individual role is defined below.

  Work constructively and respectfully with your teammates.
  The goal is to create beautiful, meaningful poetry.
  Support each other's expertise while offering honest feedback.

  Remember: the final poem is our collective achievement.

# Which specialists are in this team
agents:
  - poet-specialist
  - critic-specialist
  - creative-1
  - creative-2
```

### Layer 3: Workflows (YAML with Logic)

Define the process, stages, dependencies, data flow.

```
/server/agents/workflows/
├── create-poem.yaml
├── review-code.yaml
├── security-audit.yaml
└── [any-process].yaml
```

**Example: create-poem.yaml**
```yaml
name: create-poem
description: "Create a 4-line poem through collaborative deliberation"

# Which team works on this
team: team-poetry

# The process
blocks:
  # Stage 1: Brainstorm ideas
  - stage: ideation
    agents: [creative-1, creative-2]
    prompt: |
      Brainstorm poem themes and ideas.
      Generate 5 unique themes with brief descriptions.
      Focus on: emotion, imagery, universality.
      Output as JSON array of themes.
    parallel: true
    save_as: ideation_results.json

  # Stage 2: Write first draft
  - stage: first-draft
    agents: [poet-specialist]
    prompt: |
      Based on these ideas from the brainstorm:

      {{ ideation_results.json }}

      Write 4 lines of poetry that:
      - Follow proper meter
      - Use coherent rhyme scheme
      - Evoke the chosen theme
      - Sound natural when read aloud

      Output as JSON with 'lines' array and 'rationale'.
    depends_on: ideation
    save_as: draft.json

  # Stage 3: Critical review
  - stage: review
    agents: [critic-specialist]
    prompt: |
      Review this poem draft:

      {{ draft.json }}

      Provide honest critique:
      - Technical issues (meter, rhyme, rhythm)
      - Emotional impact and effectiveness
      - Specific improvement suggestions
      - What works well and should be preserved?

      Output as JSON with 'issues', 'suggestions', 'strengths' arrays.
    depends_on: first-draft
    save_as: review.json

  # Stage 4: Final revision
  - stage: finalize
    agents: [poet-specialist]
    prompt: |
      Original draft:
      {{ draft.json }}

      Critic feedback:
      {{ review.json }}

      Revise the poem incorporating the feedback while:
      - Preserving the original intent and emotional core
      - Fixing technical issues identified
      - Maintaining natural, flowing rhythm
      - Keeping it exactly 4 lines

      Output as JSON with 'final_lines', 'changes' arrays, and 'ready_for_publication' boolean.
    depends_on: review
    save_as: final-poem.json
```

### Layer 4: Dog Orchestrator

Dog reads all above and executes:

1. **Read workflow** (create-poem.yaml)
2. **Read team** (team-poetry.yaml) → get tone
3. **For each block:**
   - Read specialist instructions from MD files
   - Substitute team tone
   - Substitute prompt with block's prompt
   - Substitute data placeholders ({{ file.json }})
   - Call Claude API with full context
   - Save result to file
   - Log everything
4. **Manage:** dependencies, parallelism, data flow

## Key Mechanisms

### 1. DRY Principle
Each agent defined once, used everywhere:
```
poet-specialist.md → used in 5 workflows, 3 teams
tester.md → used in code-review, security-audit, qa-workflow
```

### 2. Reusability
One agent across different teams/workflows:
```yaml
# create-poem.yaml
agents: [poet-specialist]

# review-blog.yaml
agents: [poet-specialist, critic-specialist]

# Both use same MD file
```

### 3. Composability
Mix agents freely:
```yaml
agents: [creative-1, creative-2]  # 2 in parallel
agents: [poet-specialist]          # 1
agents: [poet, critic, integrator] # 3 sequential
```

### 4. Parallelism
```yaml
- stage: brainstorm
  agents: [creative-1, creative-2]
  parallel: true    # Both run simultaneously
```

### 5. Dependencies
```yaml
- stage: draft
  depends_on: ideation   # Wait for ideation to finish

- stage: review
  depends_on: draft      # Wait for draft
```

### 6. Data Flow
```yaml
prompt: |
  Based on ideas from ideation:
  {{ ideation_results.json }}    # Input from previous stage

  Write draft incorporating them.
```

### 7. Logging
Dog logs everything:
```
/tmp/dog-runs/run-TIMESTAMP/
├── dog.log          # All events: STARTED, COMPLETED, FAILED
├── dog.db           # SQLite: process state
├── summary.json     # Final: total, completed, failed
├── metadata.json    # Config: agents, semaphore, timeout
└── logs/
    ├── stage-1-ideation-creative-1.log
    ├── stage-1-ideation-creative-2.log
    ├── stage-2-draft-poet-specialist.log
    ├── stage-3-review-critic-specialist.log
    └── stage-4-finalize-poet-specialist.log
```

## Example: How Dog Executes

```bash
./dog-cli.sh run create-poem.yaml
```

**Dog does:**

```
1. Parse create-poem.yaml
2. Load team-poetry.yaml → tone
3. Load specialists: poet-specialist.md, critic-specialist.md, creative-1.md, creative-2.md

4. Execute block "ideation":
   - Load creative-1.md, creative-2.md
   - Prepend tone from team-poetry.yaml
   - Add prompt: "Brainstorm poem themes..."
   - Call: claude_api(FULL_PROMPT)
   - Save result to ideation_results.json
   - Log: PROCESS COMPLETED stage-1-ideation

5. Wait (depends_on not needed for first block)

6. Execute block "first-draft":
   - Load poet-specialist.md
   - Prepend tone
   - Load ideation_results.json
   - Substitute {{ ideation_results.json }} in prompt
   - Add prompt with substitution
   - Call: claude_api(FULL_PROMPT_WITH_CONTEXT)
   - Save result to draft.json
   - Log: PROCESS COMPLETED stage-2-draft

7. Execute block "review":
   - Load critic-specialist.md
   - Prepend tone
   - Load draft.json
   - Substitute {{ draft.json }} in prompt
   - Call: claude_api(FULL_PROMPT)
   - Save result to review.json
   - Log: PROCESS COMPLETED stage-3-review

8. Execute block "finalize":
   - Load poet-specialist.md
   - Prepend tone
   - Load BOTH draft.json AND review.json
   - Substitute BOTH in prompt
   - Call: claude_api(FULL_PROMPT_WITH_ALL_CONTEXT)
   - Save result to final-poem.json
   - Log: PROCESS COMPLETED stage-4-finalize

9. Summary: 4/4 completed, 0 failed
10. All results in /tmp/dog-runs/run-TIMESTAMP/
```

## Advantages

| Aspect | Benefit |
|--------|---------|
| **Scalability** | 50 agents, infinite combinations |
| **DRY** | Change agent once, update everywhere |
| **Speed** | New workflow? Just YAML, no code |
| **Flexibility** | Any process, any complexity |
| **Reusability** | Agents, teams, workflows all reusable |
| **Traceability** | Dog logs everything |
| **Parallelism** | Execute agents in parallel when possible |
| **Maintainability** | Specialists in MD, logic in YAML |
| **Production-ready** | Already works with current Dog |

## Implementation Phases

### Phase 1: Infrastructure (Week 1)
```bash
mkdir -p /server/agents/specialists
mkdir -p /server/agents/teams
mkdir -p /server/agents/workflows

# Create first batch of specialists
touch /server/agents/specialists/{analyst,designer,developer,tester,critic}.md
```

### Phase 2: Extend Dog (Week 2-3)
- Parse `agents:` key in YAML
- Read specialist instructions from MD files
- Read team tone from teams/*.yaml
- Substitute team tone into prompt
- Substitute {{ file.json }} placeholders
- Integrate Claude API calls
- Enhanced logging

### Phase 3: Management UI (Week 4)
- CRUD system for specialists
- CRUD system for teams
- CRUD system for workflows
- Web dashboard showing active runs
- Specialist library browser

## Comparison with Current Approaches

| System | Dog MVP | Conductor | New Architecture |
|--------|---------|-----------|-----------------|
| **Scope** | Simple commands | 3-round deliberation | Any workflow |
| **Agents** | None (just commands) | Implicit | Explicit (50+) |
| **Reuse** | No | Limited | Maximum |
| **Data flow** | No (independent) | Yes (between rounds) | Yes (explicit) |
| **Parallelism** | Via semaphore | No | Via parallel: true |
| **Complexity** | Low | Medium | Any |

## Real-World Examples

**Example 1: Poetry Creation** (shown above)
```
Ideation (2 agents) → Draft (1 agent) → Review (1 agent) → Finalize (1 agent)
```

**Example 2: Code Review**
```
Analysis (developer) → Security review (security-expert)
→ Performance review (performance-specialist)
→ Final approval (senior-reviewer)
```

**Example 3: Content Creation**
```
Research (researcher) → Write (writer) → Edit (editor)
→ SEO optimize (seo-specialist) → Publish (publisher)
```

**Example 4: Product Development**
```
Spec (product-manager) → Design (designer) → Dev (developer)
→ Test (tester) → Security audit (security) → Deploy (devops)
```

All defined as YAML, all specialists reusable, all logged by Dog.

## Status

- **Concept:** Finalized
- **Architecture:** Designed
- **Proof of Concept:** Ready (use current Dog + Claude API wrapper)
- **Full Implementation:** Proposed for Phase 2.5 of Dog
- **Discussion:** Open for feedback

## Next Steps

1. Discuss architecture with team
2. Create first 10 specialist MD files
3. Create example teams (poetry, code-review, content)
4. Extend Dog to support this architecture
5. Build management UI (optional, Phase 3)

## References

- Dog MVP v1.0: `/server/scripts/agent-pm2-dog/dog.py`
- Poetry Example: `/server/scripts/agent-pm2-dog/POETRY_EXAMPLE.md`
- Production Guide: `/server/scripts/agent-pm2-dog/PRODUCTION_GUIDE.md`
- Memory Document: `doc_07aaa9e6`
