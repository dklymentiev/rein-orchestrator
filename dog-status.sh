#!/bin/bash

# Quick Dog Status - Show last 2 workflows (previous + latest)

RUNS_DIR="/tmp/dog-runs"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}Dog Status - Last 2 Workflows${NC}"
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo ""

# Get last 2 runs
count=0
ls -td "$RUNS_DIR"/run-* 2>/dev/null | head -2 | while read run_dir; do
    count=$((count + 1))
    run_id=$(basename "$run_dir" | sed 's/run-//')
    summary="$run_dir/summary.json"
    
    if [ "$count" -eq "1" ]; then
        label="LATEST"
        label_color=$CYAN
    else
        label="PREVIOUS"
        label_color=$BLUE
    fi
    
    if [ -f "$summary" ]; then
        total=$(jq -r '.total_agents' "$summary")
        completed=$(jq -r '.completed' "$summary")
        failed=$(jq -r '.failed' "$summary")
        start_time=$(jq -r '.start_time' "$summary")
        
        # Status icon
        if [ "$completed" -eq "$total" ]; then
            icon="✓"
            icon_color=$GREEN
            status="COMPLETE"
        elif [ "$failed" -gt "0" ]; then
            icon="✗"
            icon_color=$RED
            status="FAILED"
        else
            icon="⟳"
            icon_color=$YELLOW
            status="RUNNING"
        fi
        
        # Print
        echo -e "${label_color}[${label}]${NC} $run_id"
        echo -e "  ${icon_color}${icon} Status:${NC} $status"
        echo -e "  ${BLUE}Time:${NC} $start_time"
        echo -e "  ${BLUE}Result:${NC} $completed/$total agents completed, $failed failed"
        echo ""
    fi
done

echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo "For details:"
echo "  ./dog-history.sh 10         # Show history (last 10)"
echo "  ./dog-history.sh 10 latest  # Show latest details"
