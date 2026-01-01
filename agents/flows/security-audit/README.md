# Flow: Security Audit

**Team:** team-security-audit
**Specialists:** security-expert-specialist, architect-specialist, debugger-specialist, analyst-specialist

## Description

Comprehensive security audit workflow with parallel expert perspectives:
- Threat modeling and analysis
- Vulnerability scanning
- Architecture security review
- Compliance analysis
- Integrated risk assessment and remediation roadmap

## Blocks

### 1. Threat Analysis (threat_analysis.json)
Security expert identifies threats and attack vectors.

**Enhancement:** logic/enhance-threats.py
- Calculates risk scores (severity × likelihood)
- Adds risk summary metrics
- Prioritizes threats

### 2. Vulnerability Scan (vulnerability_scan.json)
Debugger conducts detailed vulnerability assessment.

**Validation:** logic/validate-vulnerabilities.py
- Validates vulnerability structure
- Counts by severity (Critical/High/Medium/Low)
- Checks for required fields

**Parallel:** Yes (runs with architecture-security and compliance-check)

### 3. Architecture Security (architecture_security.json)
Architect evaluates security design and defense-in-depth.

**Parallel:** Yes (runs with vulnerability-scan and compliance-check)

### 4. Compliance Check (compliance_check.json)
Analyst identifies compliance gaps and requirements.

**Parallel:** Yes (runs with vulnerability-scan and architecture-security)

### 5. Final Audit Report (audit_report.json)
Integrator synthesizes all findings into comprehensive report.

**Enhancement:** logic/generate-audit-summary.py
- Creates executive summary
- Categorizes risk level (LOW/MEDIUM/HIGH/CRITICAL)
- Adds audit metadata

## Data Flow

```
Threat Analysis
Vulnerability Scan    } (parallel)
Architecture Security }
Compliance Check      }
    ↓
Final Audit Report (depends on all 4)
    ↓
Risk Summary
```

## Logic Scripts

### enhance-threats.py
- **Phase:** post (after threat-analysis)
- **Input:** threat_analysis.json
- **Calculates:** Risk scores (severity × likelihood)
- **Adds:** Risk summary, average/max scores
- **Output:** Enhanced threat analysis

### validate-vulnerabilities.py
- **Phase:** validate (after vulnerability-scan)
- **Input:** vulnerability_scan.json
- **Checks:** Structure, required fields, severity counts
- **Output:** Validates or fails with counts

### generate-audit-summary.py
- **Phase:** post (after final-audit-report)
- **Input:** audit_report.json
- **Adds:** Metadata, executive summary, risk category
- **Categorizes:** Risk (LOW/MEDIUM/HIGH/CRITICAL)
- **Output:** Final audit report with summary

## Risk Categories

Based on security rating:
- **8-10:** LOW risk
- **6-8:** MEDIUM risk
- **4-6:** HIGH risk
- **0-4:** CRITICAL risk

## Example Run

```bash
cd /server/scripts/agent-pm2-dog
python3 dog.py agents/flows/security-audit/security-audit.yaml
```

## Results

- `threat_analysis.json` - Threat modeling with risk scores
- `vulnerability_scan.json` - Vulnerability assessment
- `architecture_security.json` - Architecture security evaluation
- `compliance_check.json` - Compliance gaps analysis
- `audit_report.json` - Comprehensive audit with summary and remediation plan

## Parallelism

Multiple evaluation blocks run in parallel:
- Vulnerability scanning
- Architecture security review
- Compliance analysis

All feed into final integrated audit report.

```
Timeline:
  T0: threat-analysis starts
  T0+X: vulnerability-scan + architecture-security + compliance-check start (parallel)
  T0+Y: final-audit-report starts (depends on all 4)
```

## Executive Summary Metrics

The audit generates:
- **Overall Rating:** 0-10 scale
- **Risk Level:** Described assessment
- **Risk Category:** LOW/MEDIUM/HIGH/CRITICAL
- **Critical Issues:** Count
- **High Issues:** Count
- **Remediation Items:** Total items in plan
- **Estimated Effort:** Hours to remediate

## Future Enhancements

1. Real-time CVSS scoring
2. Compliance report export (GDPR, HIPAA, PCI-DSS)
3. Trend analysis over time
4. Integration with vulnerability databases
5. Automated remediation suggestions
6. Executive report generation (PDF/HTML)
7. Automated risk tracking
