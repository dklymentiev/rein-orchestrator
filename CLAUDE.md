# Claude Instructions for Rein

## Testing

```bash
python3 -m pytest tests/ -q
```

Characterization tests require real API keys and are slow. Run separately:
```bash
REGENERATE_GOLDEN=1 python3 -m pytest tests/test_characterization.py
```

## Key Architecture

- `run_count` (in_count): how many times routing directed to a block. Used for loop protection (max_runs).
- `completed_runs` (out_count): how many times block actually finished. Used for step mode resume.
- These are separate counters. Do not conflate them.
