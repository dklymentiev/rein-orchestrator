# Rein Security Policy - File Access Isolation

**Version:** 3.1.0+
**Date:** 2026-01-04
**Status:** ACTIVE

---

## OVERVIEW

Rein workflows execute user-provided logic scripts with Claude CLI access. Without proper isolation, logic scripts can access:
- Rein source code (`/server/scripts/rein/`)
- Other tasks (`/server/agents/tasks/`)
- Server infrastructure (`/server/hq/`, `/server/sites/`)

This policy enforces **task directory isolation** to prevent unintended file access.

---

## RULES

### RULE 1: Task Directory Isolation (MANDATORY)

All logic scripts MUST run with `cwd=task_dir`:

```python
# rein.py _run_logic()
subprocess.run(
    [interpreter, script_path],
    cwd=self.task_dir,  # MANDATORY - v3.1.0+
    input=context_json,
    ...
)
```

**Rationale:**
- Logic scripts start in task directory, not Rein directory
- Prevents accidental access to `/server/scripts/rein/rein.py`
- Each task isolated from others

**Implemented:** rein.py:662, rein.py:671

---

### RULE 2: Default Directory Access Restriction

If `task_input.add_dirs` not specified, default to task directory only:

```python
# run-specialist.py
if not add_dirs and task_path:
    add_dirs = [str(task_path)]  # Restrict to task dir
```

**Rationale:**
- Explicit > implicit
- Users must explicitly grant access to other directories
- Prevents broad file system access by default

**Implemented:** run-specialist.py:192-195

---

### RULE 3: Workflow Type Declaration (RECOMMENDED)

Workflows should declare type for appropriate restrictions:

```yaml
schema_version: "2.5.3"
name: my-workflow
workflow_type: code|product|generic  # RECOMMENDED
```

**Types:**
- `code`: Code analysis workflows - broader file access allowed
- `product`: Product/strategy workflows - restricted to task_dir
- `generic`: General purpose - restricted by default

**Status:** Recommended for v3.1.0, may be required in v4.0+

---

### RULE 4: Task File Content Embedding (OPTIONAL)

For product/strategy workflows, embed task_file content instead of path:

```python
# run-specialist.py (future enhancement)
if task_input.get('embed_task_file', False):
    with open(task_input['task_file']) as f:
        content = f.read()
    prompt = prompt.replace('{{ task.input.task_file }}', content)
```

**Rationale:**
- Removes need for Claude to Read external files
- All context in prompt - no exploration needed

**Status:** Planned for v3.2.0

---

### RULE 5: Absolute Paths for Logic Scripts

Workflow YAML logic paths should be relative to `workflow_dir`:

```yaml
logic:
  pre: logic/run-specialist.py  # Resolved to workflow_dir/logic/...
```

NOT relative to task_dir.

**Rationale:**
- Logic scripts are part of workflow definition
- Should not be affected by task isolation

**Current behavior:** Correct (workflow_dir used)

---

## ENFORCEMENT

### v3.1.0 (Current):
- ✅ subprocess.run() uses `cwd=task_dir`
- ✅ add_dirs defaults to `[task_dir]` if not specified
- ⚠️  Workflow type declaration optional (warning logged)

### v3.2.0 (Planned):
- ✅ Task file content embedding available
- ✅ Workflow type declaration enforced (fail if missing)
- ✅ Validation warns if logic script tries to access parent dirs

### v4.0.0 (Future):
- ✅ Strict mode: File access outside task_dir requires explicit approval
- ✅ Audit logging for all file access attempts
- ✅ Sandboxed execution option (Docker/container per task)

---

## MIGRATION GUIDE

### v3.0 → v3.1 Breaking Changes

**Change:** Logic scripts now run with `cwd=task_dir` instead of `cwd=workflow_dir`

**Impact:**
- Custom logic scripts that assume `os.getcwd() == workflow_dir` will break
- Scripts using relative paths may fail

**Fix:**
```python
# OLD (v3.0 - BROKEN in v3.1)
with open('workflow.yaml') as f:  # Assumes cwd=workflow_dir

# NEW (v3.1 - CORRECT)
workflow_dir = context['workflow_dir']  # From stdin context
with open(f"{workflow_dir}/workflow.yaml") as f:
```

**Check your scripts:**
```bash
grep -r "os.getcwd\|open('\|open(\"" /server/agents/flows/*/logic/*.py
```

---

## TESTING

### Verify Task Isolation

```bash
# Create test task
mkdir -p /tmp/test-task
echo "test content" > /tmp/test-task/allowed.txt

# Create restricted file
echo "secret" > /server/scripts/rein/restricted.txt

# Run workflow with test logic
cat > /tmp/test-logic.py << 'EOF'
import os
print(f"CWD: {os.getcwd()}")

# Should succeed (task dir)
with open('allowed.txt') as f:
    print(f"Allowed: {f.read()}")

# Should fail (outside task dir)
try:
    with open('/server/scripts/rein/restricted.txt') as f:
        print(f"FAIL: Read restricted file")
except:
    print("PASS: Restricted file blocked")
EOF

./rein.py --flow test-isolation
```

---

## INCIDENT RESPONSE

If logic script accessed unauthorized files:

1. **Identify scope:** Check logs for file paths accessed
2. **Review task:** Examine task_input, add_dirs settings
3. **Fix workflow:** Add explicit restrictions
4. **Redeploy:** Apply v3.1.0+ with isolation fixes

---

## KNOWN LIMITATIONS

### v3.1.0:

1. **Claude CLI bypass:** Claude Code may ignore add_dirs restrictions
   - Mitigation: Use relative paths, rely on cwd isolation
   - Future: Implement strict sandboxing (v4.0)

2. **Absolute paths work:** Logic scripts can still use `/absolute/paths`
   - Mitigation: Code review, audit logging
   - Future: Path validation middleware

3. **Symlinks:** Symlinks can bypass directory restrictions
   - Mitigation: Avoid symlinks in workflows
   - Future: Symlink resolution checks

---

## CHANGELOG

### v3.1.0 (2026-01-04)
- Added `cwd=task_dir` to subprocess.run() calls
- Added default `add_dirs=[task_dir]` restriction
- Created SECURITY-POLICY.md
- Documented migration guide

### v3.0.0 (2025-01-02)
- Block-level directory isolation
- Task directory structure (task/block/inputs|outputs|logs)

### v2.5.4 (2024-12-28)
- State machine support
- Conditional transitions

---

## REFERENCES

- Issue: "Product Team analyzing Rein code instead of task"
- Root Cause: `/server/agents/tasks/saas-wizard-review/REPORT-file-access-issue.md`
- Fix PR: TBD
- Discussion: Memory doc_[TBD]

---

## CONTACT

Security concerns: admin@generic-app.com
Policy questions: Create issue in /server/scripts/rein/
Emergency: Signal critical security issue in Discord
