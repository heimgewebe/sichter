#!/usr/bin/env bash

# Function to validate repository and branch names
# Allows alphanumeric characters, hyphens, underscores, periods, and forward slashes
validate_name() {
    local name="$1"
    if [[ -z "$name" ]]; then
        echo "Error: Name is empty." >&2
        exit 1
    fi
    if ! echo "$name" | grep -Eq '^[a-zA-Z0-9_./-]+$'; then
        echo "Error: Invalid name \"$name\". Only alphanumeric characters, hyphens, underscores, periods, and forward slashes are allowed." >&2
        exit 1
    fi
    return 0
}
