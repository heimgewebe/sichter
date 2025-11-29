#!/usr/bin/env bash
set -euo pipefail

export HAUSKI_PROFILE="$HOME/sichter/profile.yml"
export HAUSKI_ORG="${HAUSKI_ORG:-heimgewebe}"
export HAUSKI_REMOTE_BASE="${HAUSKI_REMOTE_BASE:-$HOME/sichter/repos}"
export HAUSKI_WORKTREE_BASE="${HAUSKI_WORKTREE_BASE:-$HOME/sichter/pr-worktrees}"
export HAUSKI_PR_INTERVAL="${HAUSKI_PR_INTERVAL:-300}"
alias review='pr-review --local --fast --heavy'
alias review-deep='pr-review --local --heavy'
alias review-quick='pr-review --local --fast'
# einmalig in der Shell-Session:
export HAUSKI_AUTO_APPLY=1
export HAUSKI_AUTO_COMMIT=1
# optional: Draft-PR erzeugen, falls keiner offen:
export HAUSKI_AUTO_PR=1

# danach einfach:
~/sichter/hooks/post-run
export HAUSKI_AUTO_DIRECT=0 # 0 = niemals direkt pushen

# Contract- und Policy-Defaults (nur setzen, wenn nicht bereits konfiguriert)
if [ -z "${METAREPO_CONTRACTS:-}" ] && [ -d "$HOME/repos/metarepo/contracts" ]; then
  export METAREPO_CONTRACTS="$HOME/repos/metarepo/contracts"
fi

# Semgrep kann optional via hauski hooks/CI genutzt werden
if [ -z "${SEMGREP_RULES:-}" ] && [ -f "$HOME/repos/metarepo/.semgrep.yml" ]; then
  export SEMGREP_RULES="$HOME/repos/metarepo/.semgrep.yml"
fi
