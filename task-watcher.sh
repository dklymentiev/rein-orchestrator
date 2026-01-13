#!/bin/bash
# Task Watcher - monitors for pending tasks and runs Rein
# Usage: ./task-watcher.sh [--once]

TASKS_DIR="/server/agents/tasks"
LOCK_FILE="/tmp/rein-task-watcher.lock"
LOG_FILE="/var/log/rein-task-watcher.log"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

run_task() {
    local task_dir="$1"
    local task_id=$(basename "$task_dir")
    local trigger_file="$task_dir/state/trigger.sh"
    local status_file="$task_dir/state/status.json"

    if [ ! -f "$trigger_file" ]; then
        return
    fi

    # Check if already running or completed
    if [ -f "$status_file" ]; then
        local status=$(cat "$status_file" | grep -o '"status": *"[^"]*"' | cut -d'"' -f4)
        if [ "$status" != "pending" ]; then
            return
        fi
    fi

    log "${GREEN}[START]${NC} $task_id"

    # Update status to running
    if [ -f "$status_file" ]; then
        sed -i 's/"status": "pending"/"status": "running"/' "$status_file"
        sed -i "s/\"started_at\": null/\"started_at\": \"$(date -Iseconds)\"/" "$status_file"
    fi

    # Run the trigger script
    bash "$trigger_file"
    local exit_code=$?

    # Update status based on exit code
    if [ $exit_code -eq 0 ]; then
        log "${GREEN}[COMPLETE]${NC} $task_id"
        if [ -f "$status_file" ]; then
            sed -i 's/"status": "running"/"status": "completed"/' "$status_file"
            sed -i "s/\"completed_at\": null/\"completed_at\": \"$(date -Iseconds)\"/" "$status_file"
        fi
    else
        log "${RED}[FAILED]${NC} $task_id (exit code: $exit_code)"
        if [ -f "$status_file" ]; then
            sed -i 's/"status": "running"/"status": "failed"/' "$status_file"
            sed -i "s/\"error\": null/\"error\": \"Exit code $exit_code\"/" "$status_file"
        fi
    fi

    # Remove trigger file to mark as processed
    rm -f "$trigger_file"
}

check_pending_tasks() {
    for task_dir in "$TASKS_DIR"/task-*; do
        [ -d "$task_dir" ] || continue
        run_task "$task_dir"
    done
}

# Main
if [ "$1" == "--once" ]; then
    # One-shot mode
    check_pending_tasks
    exit 0
fi

# Daemon mode
if [ -f "$LOCK_FILE" ]; then
    pid=$(cat "$LOCK_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        echo "Watcher already running (PID $pid)"
        exit 1
    fi
fi

echo $$ > "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

log "Task watcher started (PID $$)"

while true; do
    check_pending_tasks
    sleep 5
done
