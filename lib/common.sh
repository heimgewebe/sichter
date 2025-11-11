#!/usr/bin/env bash

# Function to validate repository and branch names
# Allows alphanumeric characters, hyphens, underscores, periods, and forward slashes
validate_name() {
  local name="$1"
  if [[ -z "$name" ]]; then
    echo "Error: Name is empty." >&2
    return 1
  fi
  if ! echo "$name" | grep -Eq '^[a-zA-Z0-9_.\/-]+$'; then
    echo "Error: Invalid name \"$name\". Only alphanumeric characters, hyphens, underscores, periods, and forward slashes are allowed." >&2
    return 1
  fi
  return 0
}

# Non-fatal version of validate_name for use in non-critical CI steps
validate_name_non_fatal() {
    if ! validate_name "$1"; then
        # The error message is already printed by validate_name
        return 0
    fi
    return 0
}
