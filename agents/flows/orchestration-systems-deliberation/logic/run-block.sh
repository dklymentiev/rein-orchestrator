#!/bin/bash
# Run specialist block using claude-wrapper (CLI mode with file access)
#
# Usage: ./run-block.sh <block_name> <workflow_dir>
# Example: ./run-block.sh prompt_engineer_initial /path/to/workflow
#
# This script:
# 1. Reads the prompt from the YAML config
# 2. Calls claude-wrapper in CLI mode
# 3. Claude can read real files (Dog/Conductor source code)
# 4. Saves result to block_name.json

BLOCK_NAME="${1:-}"
WORKFLOW_DIR="${2:-$(pwd)}"

if [ -z "$BLOCK_NAME" ]; then
    echo "Usage: $0 <block_name> <workflow_dir>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WRAPPER_DIR="/server/scripts/claude-wrapper"

echo "[START] Block: $BLOCK_NAME"
echo "[DIR] Workflow: $WORKFLOW_DIR"

# Run the Python logic script
python3 "$SCRIPT_DIR/run-specialist.py" \
    "$BLOCK_NAME" \
    "$WORKFLOW_DIR" \
    "Analyze the orchestration systems" \
    "$@"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[OK] Block $BLOCK_NAME completed"
else
    echo "[ERROR] Block $BLOCK_NAME failed with code $EXIT_CODE"
fi

exit $EXIT_CODE
