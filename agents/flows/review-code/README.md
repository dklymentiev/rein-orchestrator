# Flow: Review Code

**Team:** team-code-review
**Specialists:** developer-specialist, architect-specialist, tester-specialist

## Description

Comprehensive code review workflow with parallel expert perspectives:
- Architecture analysis
- Implementation quality assessment
- Testing strategy evaluation
- Integrated synthesis and recommendations

## Blocks

### 1. Architecture Review (architecture_review.json)
Senior architect evaluates system design and structure.

**Enhancement:** logic/format-architecture.py
- Formats review output
- Adds metadata

### 2. Implementation Review (implementation_review.json)
Developer assesses code quality and standards compliance.

**Validation:** logic/validate-code-quality.sh
- Validates review structure using jq
- Checks required fields
- Counts severity issues

**Parallel:** Yes (runs simultaneously with testing-review)

### 3. Testing Review (testing_review.json)
QA expert evaluates testing approach and coverage.

**Parallel:** Yes (runs simultaneously with implementation-review)

### 4. Synthesis (review_synthesis.json)
Integrator synthesizes all three perspectives.

**Enhancement:** logic/generate-report.py
- Creates consolidated report
- Calculates approval status
- Adds report metadata

## Data Flow

```
Architecture Review
Implementation Review  } (parallel)
Testing Review        }
    ↓
Synthesis (depends on all 3)
    ↓
Final Report
```

## Logic Scripts

### format-architecture.py
- **Phase:** post (after architecture-review)
- **Input:** architecture_review.json
- **Adds:** processed flag, review_type, recommendation count
- **Output:** enhanced review

### validate-code-quality.sh
- **Phase:** validate (after implementation-review)
- **Input:** implementation_review.json
- **Checks:** Required fields (code_quality, strengths, improvements)
- **Counts:** Severity issues
- **Output:** validates or fails

### generate-report.py
- **Phase:** post (after synthesis)
- **Input:** review_synthesis.json
- **Adds:** Report metadata, approval status
- **Output:** Final consolidated report

## Example Run

```bash
cd /server/scripts/agent-pm2-dog
python3 dog.py agents/flows/review-code/review-code.yaml
```

## Results

- `architecture_review.json` - Architecture analysis
- `implementation_review.json` - Code quality assessment
- `testing_review.json` - Testing evaluation
- `review_synthesis.json` - Integrated report with approval

## Parallelism

Implementation and testing reviews run in parallel for efficiency.
Architecture review runs first (foundation for synthesis).

```
Timeline:
  T0: architecture-review starts
  T0+X: implementation-review + testing-review start (parallel)
  T0+Y: synthesis starts (depends on all 3)
```

## Quality Thresholds

Approval based on overall_rating:
- ≥ 7/10: Approved
- < 7/10: Needs improvement

## Future Enhancements

1. Add custom quality rules
2. Export to HTML report
3. Integration with GitHub/GitLab
4. Trend analysis over time
5. Custom notification on failures
