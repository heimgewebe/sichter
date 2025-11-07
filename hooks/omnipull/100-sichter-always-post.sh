#!/usr/bin/env bash
set -euo pipefail
# wird von omnipull am Ende aufgerufen:
exec "$HOME/sichter/cli/omnicheck" --changed
