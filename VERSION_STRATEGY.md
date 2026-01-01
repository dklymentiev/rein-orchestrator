# Version Strategy: Incremental Development

**Decision:** Work with new versions, don't modify current code
**Approach:** dog-v1.py → dog-v2.py → dog.py (final)

## Benefits

✓ **Safe:** Current code stays intact
✓ **Testable:** Can run both versions in parallel
✓ **Traceable:** Clear version history
✓ **Reversible:** Easy to rollback if needed

## Version Naming

| File | Purpose | Status |
|------|---------|--------|
| `dog-v1-archive/dog.py` | Old implementation (shell execution) | Archived |
| `dog-v2.py` | New implementation (Claude API) | In development |
| `dog.py` | Final production version | TBD (after v2 complete) |

## Development Process

1. **Phase 2.5-A:** Write dog-v2.py
   - Test with `python3 dog-v2.py agents/workflows/create-poem.yaml`
   - Keep dog-cli.sh pointing to dog.py (unchanged)

2. **Phase 2.5-B:** Create specialists & teams
   - No changes to orchestrator
   - Just populate agents/ directory

3. **Phase 2.5-C:** Testing & Validation
   - Test with `dog-v2.py`
   - Verify all features work
   - Log issues

4. **Phase 2.5-D:** Promote to Production
   - Rename dog-v2.py → dog.py
   - Update dog-cli.sh to use new dog.py
   - Archive old if needed

## Running Versions

```bash
# Old version (if still exists)
python3 dog-v1.py example.yaml

# New version (during development)
python3 dog-v2.py agents/workflows/create-poem.yaml

# Production version (after promotion)
./dog-cli.sh run agents/workflows/create-poem.yaml
# (internally calls dog.py)
```

## Current Status

- dog-v1: Archived in `dog-v1-archive/`
- dog-v2: Created with stub (8.7KB)
  - DogEngine class ✓
  - load_workflow ✓
  - load_team ✓
  - load_specialist ✓
  - assemble_prompt ✓
  - call_claude ✓
  - run_block ✓
  - execute_workflow ✓
  - Main CLI ✓
  
  To do:
  - Test with real workflow
  - Handle errors better
  - Add logging to SQLite
  - Support parallelism (parallel: true)
  - Support semaphore control
  - Integration with dog-cli.sh

- dog.py: To be created from dog-v2.py after testing

## cli Integration

```bash
# dog-cli.sh currently doesn't call any python version
# It just shows status/history from /tmp/dog-runs/

# After promotion, will need to update:
./dog-cli.sh run <workflow>
  # Will call: python3 dog.py <workflow>
```

## Risk Management

Low Risk:
- dog-v2.py coexists with production tools
- Can test independently
- Rollback easy (just don't promote)

Testing:
- Start with simple workflow (poetry)
- Then complex (code review, security)
- Full end-to-end validation before promotion

---

**Ready to develop v2!**
