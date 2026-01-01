# Workflow Generation Process

This directory contains the **Workflow Generation Pipeline** - a complete system for generating Dog workflows from natural language descriptions.

## Quick Start

### Generate a Workflow

```bash
cd /server/scripts/agent-pm2-dog

./dog.py agents/flows/workflow-generation/workflow-generation.yaml \
  --input "Create a workflow where 3 poets write poems about technology, then a judge picks the best"
```

### What You Get

The system generates:
1. **workflow-name.yaml** - The workflow (5 phase generation process → your workflow)
2. **team-workflow-name.yaml** - Team definition with specialists
3. **specialist-*.md** - Stub files for specialists (customize these)

## System Overview

### The 5-Phase Pipeline

| Phase | Block | Specialist | Input | Output |
|-------|-------|------------|-------|--------|
| 1 | analyze_requirements | analyzer-requirements | User description | Analysis JSON |
| 2 | architect_workflow | architect-workflow | Analysis | Architecture JSON |
| 3 | generate_yaml | generator-yaml | Architecture | YAML files |
| 4 | validate_schema | validator-workflow | YAML files | Validation report |
| 5 | save_workflow | (custom logic) | Validated YAML | Files on disk |

### Input Format

Provide your workflow description to the `--input` flag:

```bash
--input "Three parallel workers analyze data, then aggregator combines results, finally reporter presents"
```

### Output Files

Generated workflows appear in:
- `agents/flows/{workflow-name}/` - Workflow YAML file
- `agents/teams/team-{workflow-name}.yaml` - Team definition
- `agents/specialists/` - Specialist stub files

## The 4 Specialists

### 1. Analyzer Requirements
**File:** `../../specialists/analyzer-requirements.md`

Breaks down user requirements into structured analysis:
- Identifies workflow concept and purpose
- Extracts stages and their relationships
- Lists specialists needed
- Maps data flow and dependencies

Output: JSON analysis structure

### 2. Architect Workflow
**File:** `../../specialists/architect-workflow.md`

Designs the technical workflow structure:
- Plans block names and phases
- Arranges for parallelization
- Defines dependencies
- Classifies critical vs. resilient blocks

Output: Detailed architecture JSON

### 3. Generator YAML
**File:** `../../specialists/generator-yaml.md`

Converts architecture to production YAML:
- Generates workflow.yaml with all blocks
- Generates team.yaml with specialists
- Ensures schema_version: "2.5.3"
- Lists specialist stub files to create

Output: Valid YAML files and file list

### 4. Validator Workflow
**File:** `../../specialists/validator-workflow.md`

Validates against strict requirements:
- Checks schema structure
- Verifies no circular dependencies
- Validates block references
- Checks flow control decisions

Output: Validation report with errors/warnings

## Data Flow

Each phase passes its output to the next phase as JSON:

```
Phase 1: analyze_requirements.json
  ↓ (read as {{ analyze_requirements.json }})
Phase 2: architect_workflow.json
  ↓ (read as {{ architect_workflow.json }})
Phase 3: generate_yaml.json (contains workflow.yaml + team.yaml)
  ↓ (read as {{ generate_yaml.json }})
Phase 4: validate_schema.json
  ↓ (used for save decision)
Phase 5: Files saved to disk
```

## Schema Compliance

Every generated workflow:
- ✅ Uses `schema_version: "2.5.3"`
- ✅ Passes JSON Schema validation
- ✅ Has no circular dependencies
- ✅ Can be executed by dog.py immediately

This is enforced at Phase 4 validation.

## Validation Scripts

Each phase includes validation logic in `logic/`:

| Script | Purpose |
|--------|---------|
| validate-analysis.py | Check analysis JSON structure |
| validate-architecture.py | Check architecture feasibility |
| validate-yaml-structure.py | Check YAML syntax |
| validate-workflow.py | Full schema validation |
| save-workflow-files.py | Save to disk |

These scripts run after each specialist completes to ensure quality.

## Examples

### Example 1: Poetry Contest

Input:
```
Create a workflow where 3 poets each write a poem about technology,
then a judge picks the best one
```

Generated workflow:
- **poet_1_writes**, **poet_2_writes**, **poet_3_writes** (Phase 1, parallel)
- **judge_picks** (Phase 2, depends on all 3 poets)

Result: `agents/flows/tech-poetry-contest/`

### Example 2: Code Review

Input:
```
Three reviewers check code for security, performance, and style.
A lead architect makes final decision based on their feedback.
```

Generated workflow:
- **security_review**, **performance_review**, **style_review** (Phase 1, parallel)
- **architect_decision** (Phase 2, depends on all reviews)

Result: `agents/flows/code-review/`

### Example 3: Multi-Round Deliberation

Input:
```
First round: 3 specialists analyze a problem independently.
Second round: They see each other's analysis and refine.
Third round: Final recommendations based on synthesis.
```

Generated workflow:
- **specialist_1_round_1**, **specialist_2_round_1**, **specialist_3_round_1** (Phase 1)
- **specialist_1_round_2**, **specialist_2_round_2**, **specialist_3_round_2** (Phase 2)
- **final_synthesis** (Phase 3)

Result: `agents/flows/multi-round-deliberation/`

## Customization

### Modify Specialist Instructions

Edit the specialist files in `../../specialists/` to change how they work:

```bash
# Edit how requirements are analyzed
nano ../../specialists/analyzer-requirements.md

# Edit how YAML is generated
nano ../../specialists/generator-yaml.md
```

### Adjust Generation Prompts

Edit the prompts in `workflow-generation.yaml` to guide specialists:

```yaml
prompt: |
  Your custom instructions here.
  Make sure to {{reference_previous_phase.json}}
  Return valid JSON only.
```

### Add Validation Rules

Edit validation scripts in `logic/` to add custom checks:

```python
# Add rule to validate specialist count
if len(specialists) > 10:
    errors.append("Too many specialists")
```

### Run with Pause

Start the workflow in paused state to review each phase:

```bash
./dog.py agents/flows/workflow-generation/workflow-generation.yaml \
  --input "..." --pause
```

Then use the interactive UI to resume phase by phase.

## Troubleshooting

### Generation Failed

Check the validation report in Phase 4:
```
[ERROR] Schema validation failed at blocks.2: Block 'judge' depends on undefined block
```

Fix: Generator needs to ensure all referenced blocks exist.

### YAML Syntax Error

Error in Phase 3:
```
[ERROR] workflow.yaml YAML syntax error
```

Fix: Generator produced invalid YAML. Check Phase 3 specialist output.

### Specialist File Not Found

Error in Phase 4:
```
[WARNING] Specialist file not found: security-reviewer.md
```

Expected: Specialist stubs are created by Phase 5. Customize after generation.

## Integration with Dog

After generation, run the workflow immediately:

```bash
# Generate
./dog.py agents/flows/workflow-generation/workflow-generation.yaml \
  --input "Your description"

# Run generated workflow
./dog.py agents/flows/workflow-name/workflow-name.yaml
```

## Status

✅ 4 specialist roles defined
✅ 5-phase generation workflow
✅ Validation at every step
✅ Schema v2.5.3 compliance guaranteed
✅ Ready for production use

## Next Steps (Phase 3)

- [ ] Auto-generate full specialist markdown files
- [ ] Create template specialists for common roles
- [ ] Auto-generate test workflows
- [ ] Generate documentation
- [ ] Implement workflow versioning

## Files Reference

```
workflow-generation/
├── README.md                     (this file)
├── workflow-generation.yaml      (5-phase generation pipeline)
└── logic/
    ├── validate-analysis.py      (Phase 1 validation)
    ├── validate-architecture.py  (Phase 2 validation)
    ├── validate-yaml-structure.py (Phase 3 validation)
    ├── validate-workflow.py      (Phase 4 validation)
    └── save-workflow-files.py    (Phase 5 file save)
```

## Support

For documentation on:
- **Schema v2.5.3**: See `/PHASE_1_IMPLEMENTATION.md`
- **Validation Engine**: See `models/validator.py`
- **Block execution**: See `dog.py` ProcessManager class
- **Full guide**: See `PHASE_2_WORKFLOW_GENERATOR.md`
