#!/bin/bash

# Rein CLI - Unified interface for Rein workflow management
# Provides: status, history, logs, and other common operations

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
RUNS_DIR="/tmp/rein-runs"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Functions

show_help() {
    cat << EOF
${CYAN}${BOLD}Rein CLI - Workflow Management${NC}

${BOLD}Usage:${NC}
  rein status                    # Show last 2 workflows (quick check)
  rein history [N] [RUN_ID]      # Show last N runs or details for RUN_ID
  rein logs [RUN_ID]             # Show logs for a run (latest if not specified)
  rein run <yaml>                # Execute workflow
  rein list                      # List all runs with summary
  rein clean [N]                 # Keep only last N runs (default: 10)
  rein help                      # Show this help

${BOLD}Examples:${NC}
  rein status                    # Quick status: latest + previous
  rein history                   # Show last 10 runs
  rein history 5                 # Show last 5 runs
  rein logs                      # Show logs for latest run
  rein logs 20251231-125718      # Show logs for specific run
  rein run my-workflow.yaml      # Execute workflow
  rein list                      # List all runs (summarized)
  rein clean 20                  # Keep only last 20 runs

${BOLD}Run Directories:${NC}
  Stored in: $RUNS_DIR

${BOLD}Status Meanings:${NC}
  ✓ COMPLETE  - All agents finished successfully
  ✗ FAILED    - One or more agents failed
  ⟳ RUNNING   - Workflow still executing

EOF
}

cmd_status() {
    "$SCRIPT_DIR/rein-status.sh"
}

cmd_history() {
    local limit=${1:-10}
    local detail=${2:-}

    if [ ! -z "$detail" ]; then
        "$SCRIPT_DIR/rein-history.sh" "$limit" "$detail"
    else
        "$SCRIPT_DIR/rein-history.sh" "$limit"
    fi
}

cmd_logs() {
    local run_id=${1:-latest}

    if [ "$run_id" = "latest" ]; then
        run_dir=$(ls -td "$RUNS_DIR"/run-* 2>/dev/null | head -1)
        if [ -z "$run_dir" ]; then
            echo -e "${RED}No runs found${NC}"
            exit 1
        fi
        run_id=$(basename "$run_dir" | sed 's/run-//')
    else
        run_dir="$RUNS_DIR/run-$run_id"
        if [ ! -d "$run_dir" ]; then
            echo -e "${RED}Run not found: $run_id${NC}"
            exit 1
        fi
    fi

    echo -e "${CYAN}${BOLD}Logs for run: $run_id${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════${NC}"

    if [ -f "$run_dir/rein.log" ]; then
        echo -e "${BLUE}Main log:${NC}"
        cat "$run_dir/rein.log" | tail -30
    fi

    echo ""
    if [ -d "$run_dir/logs" ]; then
        echo -e "${BLUE}Agent logs in: $run_dir/logs/${NC}"
        ls -1 "$run_dir/logs" | while read agent_log; do
            size=$(du -h "$run_dir/logs/$agent_log" | cut -f1)
            echo "  - $agent_log ($size)"
        done
    fi
}

cmd_run() {
    local yaml=$1

    if [ -z "$yaml" ]; then
        echo -e "${RED}Usage: rein run <workflow.yaml>${NC}"
        exit 1
    fi

    if [ ! -f "$yaml" ]; then
        echo -e "${RED}File not found: $yaml${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Running: $yaml${NC}"
    cd "$SCRIPT_DIR"
    python3 rein.py "$yaml"
}

cmd_list() {
    echo -e "${CYAN}${BOLD}All Rein Runs${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"

    count=0
    ls -td "$RUNS_DIR"/run-* 2>/dev/null | while read run_dir; do
        count=$((count + 1))
        run_id=$(basename "$run_dir" | sed 's/run-//')
        summary="$run_dir/summary.json"

        if [ -f "$summary" ]; then
            total=$(jq -r '.total_agents' "$summary" 2>/dev/null || echo "?")
            completed=$(jq -r '.completed' "$summary" 2>/dev/null || echo "0")
            failed=$(jq -r '.failed' "$summary" 2>/dev/null || echo "0")
            start_time=$(jq -r '.start_time' "$summary" 2>/dev/null | cut -d'T' -f2 | cut -d'.' -f1)

            if [ "$completed" -eq "$total" ] 2>/dev/null; then
                status_color=$GREEN
                status="✓"
            elif [ "$failed" -gt "0" ]; then
                status_color=$RED
                status="✗"
            else
                status_color=$YELLOW
                status="⟳"
            fi

            printf "${BLUE}[%3d]${NC} [%s] %s ${status_color}%s${NC} %d/%d agents\n" \
                "$count" "$run_id" "$start_time" "$status" "$completed" "$total"
        fi
    done

    echo ""
}

cmd_clean() {
    local keep=${1:-10}

    echo -e "${YELLOW}Keeping last $keep runs, deleting older ones...${NC}"

    local count=0
    ls -td "$RUNS_DIR"/run-* 2>/dev/null | tail -n +$((keep+1)) | while read run_dir; do
        count=$((count + 1))
        run_id=$(basename "$run_dir")
        echo -e "${BLUE}Deleting:${NC} $run_id"
        rm -rf "$run_dir"
    done

    if [ "$count" -eq 0 ]; then
        echo -e "${GREEN}No old runs to delete (less than $keep runs exist)${NC}"
    else
        echo -e "${GREEN}Deleted $count old runs${NC}"
    fi
}

# Main

if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

cmd=$1
shift || true

case "$cmd" in
    status|st)
        cmd_status "$@"
        ;;
    history|hist|h)
        cmd_history "$@"
        ;;
    logs|log|l)
        cmd_logs "$@"
        ;;
    run|r)
        cmd_run "$@"
        ;;
    list|ls)
        cmd_list "$@"
        ;;
    clean)
        cmd_clean "$@"
        ;;
    help|-h|--help)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $cmd${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
