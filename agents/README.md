# Dog Multi-Agent Specialist System

**Phase:** 2.5 Clean Rewrite
**Created:** 2025-12-31
**Status:** Ready for implementation

## Structure

```
agents/
├── specialists/        # 50+ agent definitions (MD files)
├── teams/             # Team configurations (YAML)
└── workflows/         # Workflow definitions (YAML)
```

## Usage

```bash
cd /server/scripts/agent-pm2-dog
./dog-cli.sh run agents/workflows/create-poem.yaml
```

See README files in each subdirectory.
