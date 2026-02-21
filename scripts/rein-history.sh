#!/bin/bash

# Rein Workflow History & Results
# Shows recent workflows, their status, and detailed results

RUNS_DIR="/tmp/rein-runs"
LIMIT=${1:-10}  # Show last N workflows (default 10)
SHOW_DETAIL=${2:-}  # Optional: RUN_ID or "latest" for detailed view

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to show workflow summary
show_history() {
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Rein Workflow History - Last $LIMIT Executions${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    # Get last N runs, sorted by date
    ls -td "$RUNS_DIR"/run-* 2>/dev/null | head -$LIMIT | while read run_dir; do
        run_id=$(basename "$run_dir" | sed 's/run-//')
        summary="$run_dir/summary.json"
        
        if [ -f "$summary" ]; then
            # Parse summary.json
            total=$(jq -r '.total_agents' "$summary" 2>/dev/null || echo "?")
            completed=$(jq -r '.completed' "$summary" 2>/dev/null || echo "0")
            failed=$(jq -r '.failed' "$summary" 2>/dev/null || echo "0")
            start_time=$(jq -r '.start_time' "$summary" 2>/dev/null | cut -d'T' -f2 | cut -d'.' -f1)
            end_time=$(jq -r '.end_time' "$summary" 2>/dev/null | cut -d'T' -f2 | cut -d'.' -f1)
            
            # Calculate duration
            if [ ! -z "$end_time" ] && [ "$end_time" != "null" ]; then
                start_epoch=$(date -d "2025-12-31T$start_time" +%s 2>/dev/null || echo "0")
                end_epoch=$(date -d "2025-12-31T$end_time" +%s 2>/dev/null || echo "0")
                duration=$((end_epoch - start_epoch))
                duration_str="${duration}s"
            else
                duration_str="running"
            fi
            
            # Status
            if [ "$completed" -eq "$total" ] 2>/dev/null; then
                status_color=$GREEN
                status="✓ COMPLETE"
            elif [ "$failed" -gt "0" ]; then
                status_color=$RED
                status="✗ FAILED"
            else
                status_color=$YELLOW
                status="⟳ RUNNING"
            fi
            
            # Print row
            printf "${BLUE}[%s]${NC} %s  " "$run_id" "$start_time"
            printf "${status_color}%-12s${NC}" "$status"
            printf "  %d/%d agents  " "$completed" "$total"
            printf "Time: %s\n" "$duration_str"
        fi
    done
    
    echo ""
}

# Function to show detailed results for a workflow
show_details() {
    local run_id=$1
    
    if [ "$run_id" = "latest" ]; then
        run_dir=$(ls -td "$RUNS_DIR"/run-* 2>/dev/null | head -1)
        run_id=$(basename "$run_dir" | sed 's/run-//')
    else
        run_dir="$RUNS_DIR/run-$run_id"
    fi
    
    if [ ! -d "$run_dir" ]; then
        echo -e "${RED}Run not found: $run_id${NC}"
        exit 1
    fi
    
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Rein Workflow Details - Run $run_id${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""
    
    # Show metadata
    if [ -f "$run_dir/metadata.json" ]; then
        echo -e "${BLUE}Metadata:${NC}"
        jq . "$run_dir/metadata.json" 2>/dev/null | sed 's/^/  /'
        echo ""
    fi
    
    # Show summary
    if [ -f "$run_dir/summary.json" ]; then
        echo -e "${BLUE}Summary:${NC}"
        jq . "$run_dir/summary.json" 2>/dev/null | sed 's/^/  /'
        echo ""
    fi
    
    # Show process results from db
    if [ -f "$run_dir/rein.db" ]; then
        echo -e "${BLUE}Process Results:${NC}"
        sqlite3 -header -column "$run_dir/rein.db" \
            "SELECT name, status, exit_code, progress FROM processes ORDER BY name;" 2>/dev/null || echo "  (Database read error)"
        echo ""
    fi
    
    # Show last log entries
    if [ -f "$run_dir/rein.log" ]; then
        echo -e "${BLUE}Last Log Entries:${NC}"
        tail -20 "$run_dir/rein.log" | sed 's/^/  /'
        echo ""
    fi
    
    # Show agent logs (if any)
    if [ -d "$run_dir/logs" ]; then
        echo -e "${BLUE}Agent Logs:${NC}"
        ls -1 "$run_dir/logs" | while read agent_log; do
            size=$(du -h "$run_dir/logs/$agent_log" | cut -f1)
            echo "  - $agent_log ($size)"
        done
        echo ""
        
        # Show first agent's content
        first_log=$(ls -1 "$run_dir/logs" | head -1)
        if [ ! -z "$first_log" ]; then
            echo -e "${BLUE}First Agent Log Sample (${first_log}):${NC}"
            head -10 "$run_dir/logs/$first_log" | sed 's/^/    /'
            echo ""
        fi
    fi
}

# Main logic
if [ ! -z "$SHOW_DETAIL" ]; then
    show_details "$SHOW_DETAIL"
else
    show_history
    echo -e "${CYAN}For detailed results, run:${NC}"
    echo "  ./rein-history.sh 10 latest     # Show latest run details"
    echo "  ./rein-history.sh 10 20251231-125718  # Show specific run details"
    echo ""
fi
