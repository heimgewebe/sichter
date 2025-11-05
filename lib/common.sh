#!/usr/bin/env bash

# Function to validate repository and branch names
# Allows alphanumeric characters, hyphens, and underscores
validate_name() {
    local name="$1"
    if [[ ! "$name" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
        echo "Error: Invalid name \"$name\". Only alphanumeric characters, hyphens, underscores, and periods are allowed." >&2
        exit 1
    fi
    return 0
}
