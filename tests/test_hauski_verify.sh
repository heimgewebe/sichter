#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------------------------
# Test: hauski-verify sollte korrekt reagieren, wenn 'systemctl'
#       nicht verfügbar ist (z. B. in minimalen Containern).
#
# Erwartung: Die Ausgabe enthält die Meldung
#            "systemctl not found, skipping systemd checks."
# --------------------------------------------------------------------

# Temporär pipefail deaktivieren, da wir nur stdout prüfen wollen
set +o pipefail

OUTPUT="$(env HAUSKI_VERIFY_NO_SYSTEMCTL=1 ./bin/hauski-verify 2>/dev/null || true)"

set -o pipefail  # wieder aktivieren für nachfolgende Tests

if grep -q "systemctl not found, skipping systemd checks." <<<"$OUTPUT"; then
  echo "✅ Test passed: The script correctly handled the missing systemctl."
  exit 0
else
  echo "❌ Test failed: The script did not handle the missing systemctl as expected."
  echo "---- Output ----"
  echo "$OUTPUT"
  echo "----------------"
  exit 1
fi
