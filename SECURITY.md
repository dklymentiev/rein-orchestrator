# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 3.x     | Yes       |
| < 3.0   | No        |

## Reporting a Vulnerability

If you discover a security vulnerability in Rein, please report it responsibly. Do NOT open a public GitHub issue.

**How to report:**

- GitHub Security Advisories: https://github.com/rein-orchestrator/rein/security/advisories/new

Include as much detail as possible:

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact

We aim to acknowledge reports within 48 hours and provide a fix or mitigation plan within 7 days for critical issues.

## What Counts as a Security Issue

- API key or credential leakage through logs, error messages, or output files
- Code injection via workflow YAML, logic scripts, or specialist definitions
- Arbitrary file read/write outside intended working directories
- Prompt injection that bypasses specialist constraints to execute unintended actions
- Privilege escalation in the daemon or task-watcher components
- Denial of service through crafted workflow definitions

## What Is NOT a Security Issue

- Bugs that require the attacker to already have local shell access
- Feature requests for additional security hardening
- Issues in third-party provider APIs (report those to the provider)

## Trust Model and Accepted Risks

Rein is an orchestrator for operator-authored workflows. Certain surfaces
are trusted by design and are **not** considered vulnerabilities:

**Workflow YAML is trusted input.**
A `workflow.yaml` file is treated the same as a CI configuration or a
shell script: whoever writes it is assumed to have the same privileges as
the Rein process itself. This means:

- `logic.custom`, `logic.pre`, `logic.post`, `logic.validate`, and
  `logic.error` scripts run with full process privileges. Sandboxing is
  **not** applied to these hooks.
- The legacy `command:` block field executes its argument as a subprocess.
- Consequence: do not accept workflow YAML from untrusted sources. Treat
  the `agents/flows/` directory with the same access controls as your
  application source tree. For multi-tenant deployments, use OS-level
  user isolation via `agent.yaml` `linux_user:` (with root and unsafe
  character rejection) and filesystem permissions.

**Task input fields (`task.input.*`, `question.txt`) are not sanitized
against prompt injection.**
Task inputs are substituted verbatim into specialist prompts. A hostile
task input can instruct the model to ignore specialist constraints. This
is accepted because task creation itself requires authenticated access
(CLI, MCP with `REIN_AGENTS_DIR` pin, or the HQ API behind Authum).
Prompt-injection hardening for externally-exposed task creation is a
separate deployment-level concern handled at the ingress layer.

**Network bind defaults target Docker deployments.**
`REIN_WS_HOST` and `REIN_MCP_HOST` default to `0.0.0.0` so the daemon and
MCP server are reachable from sibling containers. Expose them only on
trusted networks (localhost, Docker bridge, WireGuard overlay, etc.).
For host installs, set `REIN_WS_HOST=127.0.0.1` and `REIN_MCP_HOST=127.0.0.1`
explicitly. The host-header allowlist (`REIN_MCP_ALLOWED_HOSTS`) is a CSRF
mitigation, not authentication.

**Environment variables are passed through to logic scripts.**
Subprocess calls inherit the parent environment so logic hooks can read
`ANTHROPIC_API_KEY` and similar. Keep Rein and its workflows in a dedicated
OS account so the ambient environment does not leak unrelated secrets.

These decisions were made deliberately and confirmed during the 3.3.0 and
3.3.1 pre-release audits. A reviewer who wants to re-open one of them
should propose an alternative that preserves the use case (Docker
deployment, operator-authored workflows, logic hook feature parity).

## Disclosure

We follow coordinated disclosure. Once a fix is released, we will credit the reporter (unless they prefer to remain anonymous) and publish an advisory describing the issue.
