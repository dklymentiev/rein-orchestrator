#!/bin/bash
# Validate-phase: Check code quality review structure

DATA_FILE=$1

# Check if file exists
if [ ! -f "$DATA_FILE" ]; then
    echo "[ERROR] Data file not found: $DATA_FILE"
    exit 1
fi

# Unwrap result if it exists (dog.py wraps output in {stage, result, timestamp})
TEMP_FILE=$(mktemp)
if jq -e '.result' "$DATA_FILE" > /dev/null 2>&1; then
    # Extract and parse the result field
    jq -r '.result' "$DATA_FILE" | jq . > "$TEMP_FILE" 2>/dev/null && mv "$TEMP_FILE" "$DATA_FILE"
fi
rm -f "$TEMP_FILE"

# Check required fields using jq
if ! jq -e '.code_quality' "$DATA_FILE" > /dev/null 2>&1; then
    echo "[ERROR] Missing 'code_quality' field"
    exit 1
fi

if ! jq -e '.strengths' "$DATA_FILE" > /dev/null 2>&1; then
    echo "[ERROR] Missing 'strengths' field"
    exit 1
fi

if ! jq -e '.improvements' "$DATA_FILE" > /dev/null 2>&1; then
    echo "[ERROR] Missing 'improvements' field"
    exit 1
fi

# Count issues
ISSUE_COUNT=$(jq '.severity_issues | length' "$DATA_FILE" 2>/dev/null || echo 0)

echo "[VALID] Code quality review validated ($ISSUE_COUNT severity issues found)"
exit 0
