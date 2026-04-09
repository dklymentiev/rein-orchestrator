# Claude Instructions for Rein

## Repository Structure

```
/server/scripts/rein/          -- DEV: working copy, daemon runs from here
/server/opensource/rein/        -- RELEASE: clean copy for GitHub push
```

## Release Flow (applies to ALL opensource projects)

```
/server/scripts/{project}      -- develop, test, commit here
        |
        v
/server/opensource/{project}   -- sync, review, push to GitHub
        |
        v
GitHub: dklymentiev/{repo}    -- public, clients pull from here
```

### Opensource projects on this server

| Project | Dev path | Opensource path | GitHub repo |
|---------|----------|-----------------|-------------|
| Rein | `/server/scripts/rein` | `/server/opensource/rein` | `dklymentiev/rein-orchestrator` |
| Mesh | `/server/scripts/mesh` | `/server/opensource/mesh` | `dklymentiev/mesh` |
| Agent Memory | `/server/scripts/agent-memory` | `/server/opensource/agent-memory` | `dklymentiev/agent-memory` |
| Screenbox | `/server/scripts/screenbox` | `/server/opensource/screenbox` | `dklymentiev/screenbox` |

### How to release

1. Commit and test in `/server/scripts/{project}`
2. `cd /server/opensource/{project}`
3. `git pull dev main` (syncs from scripts/)
4. Review changes: `git log dev/main..main` or `git diff`
5. `git push origin main` (pushes to GitHub)
6. Create tag/release on GitHub if needed

### Rules

- **NEVER push directly from /server/scripts/ to GitHub** -- always go through /server/opensource/
- **NEVER push without running tests first**
- The `/server/scripts/` remote `github` should NOT be used for push (legacy, remove if present)
- `/server/opensource/` remote `dev` points to local `/server/scripts/` path
- `/server/opensource/` remote `origin` points to GitHub

## Rein-Specific

### Running daemon

```bash
# Daemon runs from /server/scripts/rein (not opensource)
python3 -m rein --daemon --agents-dir /server/agents --max-workflows 25 --daemon-interval 2
```

### Testing

```bash
cd /server/scripts/rein
python3 -m pytest tests/ -q --ignore=tests/test_characterization.py --ignore=tests/test_containment_sweep.py --ignore=tests/test_cli.py
```

Characterization tests require real API keys and are slow. Run separately:
```bash
REGENERATE_GOLDEN=1 python3 -m pytest tests/test_characterization.py
```

### Key architecture

- `run_count` (in_count): how many times routing directed to a block. Used for loop protection (max_runs).
- `completed_runs` (out_count): how many times block actually finished. Used for step mode resume.
- These are separate counters. Do not conflate them.
