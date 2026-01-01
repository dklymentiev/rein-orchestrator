# Teams

Each team combines specialists with a shared tone/style.

**Format:** YAML (.yaml) files

**Structure:**
```yaml
name: team-poetry
tone: |
  You are part of a collaborative team...
  Your role is...
agents:
  - poet-specialist
  - critic-specialist
```

**Usage:** Referenced in workflow as `team: team-name`

See examples: `team-poetry.yaml`, `team-code-review.yaml`
