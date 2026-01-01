#!/bin/bash

# Dog Workflows - List and monitor active workflows
# Usage:
#   ./dog-workflows.sh              - List all active workflows (numbered)
#   ./dog-workflows.sh 3            - Show details for workflow #3
#   ./dog-workflows.sh 20251230-140000 - Show details for specific GUID

cd /server/scripts/agent-pm2-dog

# Find all active workflow sockets
SOCKETS=$(ls /tmp/dog-*.sock 2>/dev/null | sort)

if [ -z "$SOCKETS" ]; then
    echo "No active Dog workflows found"
    exit 0
fi

# If argument specified - show details for that workflow
if [ $# -gt 0 ]; then
    ARG="$1"

    # Check if it's a number (index in list)
    if [[ "$ARG" =~ ^[0-9]+$ ]]; then
        # Get workflow by index
        INDEX=$ARG
        GUID=$(echo "$SOCKETS" | nl -v 1 | awk -v idx="$INDEX" '$1 == idx {print}' | \
               sed 's/.*dog-//;s/.sock//')

        if [ -z "$GUID" ]; then
            echo "Workflow #$INDEX not found. Use: ./dog-workflows.sh"
            exit 1
        fi
    else
        # Treat as GUID
        GUID="$ARG"
    fi

    # Find run directory
    RUN_DIR=$(ls -d /tmp/dog-runs/run-${GUID} 2>/dev/null | head -1)

    if [ -z "$RUN_DIR" ]; then
        echo "Workflow $GUID not found"
        exit 1
    fi

    DOG_LOG="$RUN_DIR/dog.log"

    if [ ! -f "$DOG_LOG" ]; then
        echo "Log file not found for $GUID"
        exit 1
    fi

    echo "=== Workflow Details: $GUID ==="
    echo ""
    echo "Directory: $RUN_DIR"
    echo "Log: $DOG_LOG"
    echo ""

    # Get summary stats
    RUNNING=$(grep "status=running" "$DOG_LOG" | tail -1 | grep -o "running=[0-9]*" | cut -d= -f2)
    PAUSED=$(grep "status=paused" "$DOG_LOG" | tail -1 | grep -o "paused=[0-9]*" | cut -d= -f2)
    DONE=$(grep "PROCESS COMPLETED" "$DOG_LOG" | wc -l)
    FAILED=$(grep "PROCESS FAILED" "$DOG_LOG" | wc -l)
    TOTAL=$(grep -c "PROCESS STARTED" "$DOG_LOG")

    if [ "$TOTAL" -gt 0 ]; then
        PROGRESS=$((($DONE + $FAILED) * 100 / $TOTAL))
    else
        PROGRESS=0
    fi

    echo "Summary: Progress $PROGRESS% | Total: $TOTAL | Running: $RUNNING | Paused: $PAUSED | Done: $DONE | Failed: $FAILED"
    echo ""

    # Show active (running) processes
    echo "Active Processes (status=running):"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Extract unique running processes from log (last status for each)
    if grep -q "status=running" "$DOG_LOG"; then
        printf "%-40s | %-8s | %-10s\n" "Process Name" "PID" "Status"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        grep "status=running" "$DOG_LOG" | grep "PROCESS |" | awk -F'|' '{
            for(i=1; i<=NF; i++) {
                if ($i ~ /status=running/) {
                    # Extract process name from previous field
                    name = $(i-1)
                    gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
                    # Extract PID
                    for(j=i; j<=NF; j++) {
                        if ($j ~ /pid=/) {
                            pid = $j
                            gsub(/.*pid=/, "", pid)
                            gsub(/[[:space:]]+$/, "", pid)
                            break
                        }
                    }
                    printf "%-40s | %-8s | %-10s\n", name, pid, "running"
                    break
                }
            }
        }' | sort -u
    else
        echo "No running processes"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Show waiting processes
    echo "Waiting Processes (next to run):"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if grep -q "status=waiting" "$DOG_LOG"; then
        printf "%-40s | %-8s | %-10s\n" "Process Name" "PID" "Status"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

        grep "status=waiting" "$DOG_LOG" | grep "PROCESS |" | awk -F'|' '{
            for(i=1; i<=NF; i++) {
                if ($i ~ /status=waiting/) {
                    # Extract process name from previous field
                    name = $(i-1)
                    gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
                    printf "%-40s | %-8s | %-10s\n", name, "-", "waiting"
                    break
                }
            }
        }' | sort -u
    else
        echo "No waiting processes"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    exit 0
fi

# Show list of all active workflows
echo "=== Active Dog Workflows ==="
echo ""

INDEX=1
for SOCKET in $SOCKETS; do
    GUID=$(basename "$SOCKET" | sed 's/dog-//;s/.sock//')

    # Find run directory
    RUN_DIR=$(ls -d /tmp/dog-runs/run-${GUID} 2>/dev/null | head -1)

    if [ -z "$RUN_DIR" ]; then
        echo "  [$INDEX] $GUID - (directory not found)"
        INDEX=$((INDEX + 1))
        continue
    fi

    DOG_LOG="$RUN_DIR/dog.log"

    if [ ! -f "$DOG_LOG" ]; then
        echo "  [$INDEX] $GUID - (log not found)"
        INDEX=$((INDEX + 1))
        continue
    fi

    # Count processes by status
    RUNNING=$(grep -c "status=running" "$DOG_LOG" | tail -1)
    PAUSED=$(grep -c "status=paused" "$DOG_LOG" | tail -1)
    DONE=$(grep "PROCESS COMPLETED" "$DOG_LOG" | wc -l)
    FAILED=$(grep "PROCESS FAILED" "$DOG_LOG" | wc -l)

    # Get total processes count
    TOTAL=$(grep -c "PROCESS STARTED" "$DOG_LOG")

    # Calculate progress
    if [ "$TOTAL" -gt 0 ]; then
        PROGRESS=$((($DONE + $FAILED) * 100 / $TOTAL))
    else
        PROGRESS=0
    fi

    # Get start time
    START_TIME=$(grep "DOG STARTED" "$DOG_LOG" | head -1 | cut -d'|' -f1 | xargs)

    printf "  [%d] %s Progress: %3d%% | Running: %d | Paused: %d | Done: %d | Failed: %d\n" \
        "$INDEX" "$GUID" "$PROGRESS" "$RUNNING" "$PAUSED" "$DONE" "$FAILED"

    printf "      Start: %s\n" "$START_TIME"
    printf "      Dir: %s\n" "$RUN_DIR"
    printf "      Cmd: ./dog-workflows.sh %d  (or ./dog-workflows.sh %s)\n" "$INDEX" "$GUID"
    echo ""

    INDEX=$((INDEX + 1))
done

echo "Total workflows: $(echo "$SOCKETS" | wc -l)"
echo ""
echo "To see details: ./dog-workflows.sh <N>  (where N is number from list)"
echo "            or: ./dog-workflows.sh <GUID>"
echo "To send command: ./dog-cmd.sh <GUID> <command>"
