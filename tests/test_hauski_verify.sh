#!/usr/bin/env bash
set -euo pipefail

# This test verifies that the hauski-verify script correctly handles cases
# where the 'systemctl' command is not available.

# We temporarily disable pipefail because we expect hauski-verify to fail for other reasons,
# but we only care about what it prints to stdout for this test.
if (set +o pipefail; env HAUSKI_VERIFY_NO_SYSTEMCTL=1 ./bin/hauski-verify | grep -q "systemctl not found"); then
    echo "Test passed: The script correctly handled the missing systemctl."
    exit 0
else
    echo "Test failed: The script did not handle the missing systemctl as expected."
    exit 1
fi
