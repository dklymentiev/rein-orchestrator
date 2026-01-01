# Specialists

Each specialist is a reusable agent definition.

**Format:** Markdown (.md) files with instructions

**Usage:** Listed in workflow blocks as `agents: [specialist-name]`

**Example:**
```
poet-specialist.md       → loaded as "poet-specialist"
critic-specialist.md     → loaded as "critic-specialist"
```

Each file contains:
- Agent name and title
- Expertise areas
- Role and responsibilities
- Constraints and guidelines
- How to handle inputs/outputs

See examples: `poet-specialist.md`, `critic-specialist.md`
