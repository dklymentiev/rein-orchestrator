#!/bin/bash

# Rein command helper - Send commands to Rein via Unix domain socket
#
# Usage (auto-detect single workflow):
#   ./rein-cmd.sh pause processor-1
#   ./rein-cmd.sh resume processor-1
#   ./rein-cmd.sh status
#   ./rein-cmd.sh list
#
# Usage (explicit GUID or number for multiple workflows):
#   ./rein-cmd.sh 20251230-140000 pause processor-1
#   ./rein-cmd.sh 20251230-140500 status
#   ./rein-cmd.sh 1 list              (by number from ./rein-workflows.sh)
#   ./rein-cmd.sh 2 pause task-1

if [ $# -lt 1 ]; then
    echo "Usage: $0 [GUID|N] <command> [args...]"
    echo "  Single workflow: $0 status"
    echo "  Multiple workflows: $0 1 status"
    echo "  Or by GUID: $0 20251230-140000 status"
    exit 1
fi

# Known commands
KNOWN_COMMANDS="pause resume status list log cancel pause-workflow resume-workflow"

# Detect if first arg is GUID or command
# GUID format: YYYYMMDD-HHMMSS (14 digits + 1 dash = 15 chars)
FIRST_ARG="$1"
IS_COMMAND=0

for cmd in $KNOWN_COMMANDS; do
    if [ "$FIRST_ARG" = "$cmd" ]; then
        IS_COMMAND=1
        break
    fi
done

GUID=""
COMMAND=""

if [ $IS_COMMAND -eq 1 ]; then
    # First arg is a command - auto-detect socket
    COMMAND="$@"

    # Try to find available socket
    SOCKETS=$(ls /tmp/rein-*.sock 2>/dev/null | wc -l)

    if [ "$SOCKETS" -eq 1 ]; then
        # Exactly one socket - use it
        SOCKET=$(ls /tmp/rein-*.sock)
        GUID=$(basename "$SOCKET" | sed 's/.*rein-//;s/.sock//')
    elif [ "$SOCKETS" -gt 1 ]; then
        # Multiple sockets - error
        echo "Error: Multiple workflows detected. Please specify GUID or number:"
        ./rein-workflows.sh
        exit 1
    else
        # No sockets found
        echo "Error: No Rein workflows found. Start one with: python3 -m rein workflow.yaml"
        exit 1
    fi
else
    # First arg is GUID or number, rest is command
    ARG="$1"

    # Check if it's a number (index in list)
    if [[ "$ARG" =~ ^[0-9]+$ ]]; then
        # Get workflow by index from rein-workflows.sh
        INDEX=$ARG
        SOCKETS=$(ls /tmp/rein-*.sock 2>/dev/null | sort)
        GUID=$(echo "$SOCKETS" | nl -v 1 | awk -v idx="$INDEX" '$1 == idx {print}' | \
               sed 's/.*rein-//;s/.sock//')

        if [ -z "$GUID" ]; then
            echo "Error: Workflow #$INDEX not found."
            echo ""
            echo "Available workflows:"
            ./rein-workflows.sh
            exit 1
        fi
    else
        # Treat as GUID
        GUID="$ARG"
    fi

    shift
    COMMAND="$@"
    SOCKET="/tmp/rein-${GUID}.sock"
fi

if [ ! -S "$SOCKET" ]; then
    echo "Error: Rein socket not found at $SOCKET"
    echo "Is Rein running with GUID $GUID?"
    exit 1
fi

# Send command to socket
if command -v nc &> /dev/null; then
    # Use netcat if available (most reliable)
    echo "$COMMAND" | nc -U "$SOCKET"
elif command -v socat &> /dev/null; then
    # Fallback to socat
    echo "$COMMAND" | socat - UNIX-CONNECT:"$SOCKET"
else
    echo "Error: Neither 'nc' nor 'socat' found. Install one of them:"
    echo "  Ubuntu/Debian: sudo apt install netcat-openbsd"
    echo "  Or: sudo apt install socat"
    exit 1
fi
