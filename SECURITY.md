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

## Disclosure

We follow coordinated disclosure. Once a fix is released, we will credit the reporter (unless they prefer to remain anonymous) and publish an advisory describing the issue.
