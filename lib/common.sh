#!/usr/bin/env bash

# Flag to toggle JSON output, consumed by caller scripts
print_json=0 # shellcheck disable=SC2034

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

parse_common_args() {
  while (($#)); do
    case "$1" in
      --json)
        print_json=1
        ;;
      --output)
        shift
        [[ $# -gt 0 ]] || {
          echo "--output braucht einen Pfad" >&2
          exit 1
        }
        output_path="$1"
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *)
        echo "Unbekannte Option: $1" >&2
        usage
        exit 1
        ;;
    esac
    shift || true
  done

  [[ -n "$output_path" ]] || {
    echo "Der Ausgabe-Pfad darf nicht leer sein" >&2
    exit 1
  }
  outdir="$(dirname "$output_path")"
  [[ -d "$outdir" ]] || mkdir -p "$outdir"
}
