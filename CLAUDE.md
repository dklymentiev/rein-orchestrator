# Instructions for Claude

**Project:** Agent-PM2 ("Dog") - Process Manager  
**Status:** MVP Prototype (Python)  
**Language:** English (documentation), Russian (conversation)

## Project Structure

```
/server/scripts/agent-pm2-dog/
├── dog.py              # Main daemon + htop-like UI (single file, ~300 lines)
├── example.yaml        # Example workflow configuration
├── requirements.txt    # Python dependencies
├── README.md          # User documentation
├── MEMORY.md          # Project marker (guid: agent-pm2-dog-001)
└── CLAUDE.md          # This file
```

## Key Components

### dog.py

**Classes:**
- `Process` — Data class representing a managed process
- `DogState` — SQLite state management
- `ProcessManager` — Semaphore + process spawning + monitoring
- `DogUI` — Rich terminal UI (htop-like)

**Main flow:**
1. Load YAML config
2. Create ProcessManager with semaphore
3. Spawn blocks as processes
4. Monitor in background threads
5. Display htop-like UI with live updates

### Features to Add

**Phase 1 (DONE):**
- ✅ Basic process spawning
- ✅ Semaphore control
- ✅ SQLite state storage
- ✅ htop-like UI with Rich
- ✅ CPU/MEM metrics

**Phase 2 (TODO):**
- Recursive Dog spawning (child Dogs)
- Webhook integration
- Graceful shutdown with signal handling
- Queue management for overflow tasks
- Timeout enforcement

**Phase 3 (Production - Team-soft-2):**
- Go implementation (compiled daemon)
- systemd integration
- REST API for remote control
- Distributed execution
- Advanced resource quotas

## Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Run with example config
./dog.py example.yaml

# Create test config
cat > test.yaml << 'YAML'
name: test
semaphore: 2
blocks:
  - name: "task1"
    command: "sleep 5"
  - name: "task2"
    command: "sleep 3"
YAML

./dog.py test.yaml
```

## Integration Points

- **Conductor:** Can execute Dog as block type
- **mem.ai:** Save workflow results to memory
- **team-generic:** Analyzed architecture
- **team-soft-2:** Will design production version

## Related Documents

- RFC: doc_1614c5b5 (Agent-PM2 architecture)
- Pilot Use Case: alcohol-distribution-30days
- Team Generic Synthesis: Integrator recommendation (Phase 1 Shell MVP → Phase 2 Go)
