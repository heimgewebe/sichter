set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

status:
    hauski-status summary

dashboard:
    hauski-dashboard

review:
    ~/sichter/hooks/post-run

pr-review:
    ~/sichter/bin/hauski-pr-review-all

pr-watch:
    ~/sichter/bin/hauski-pr-watch

autopilot:
    ~/sichter/bin/hauski-autopilot

all:
    ~/sichter/hooks/post-run
    hauski-status summary
    hauski-dashboard
default: lint

# Lokaler Helper: Schnelltests & Linter – sicher mit Null-Trennung und Quoting
lint:
    @set -euo pipefail; \
    mapfile -d '' files < <(git ls-files -z -- '*.sh' '*.bash' || true); \
    if [ "${#files[@]}" -eq 0 ]; then echo "keine Shell-Dateien"; exit 0; fi; \
    printf '%s\0' "${files[@]}" | xargs -0 bash -n; \
    shfmt -d -i 2 -ci -sr -- "${files[@]}"; \
    shellcheck -S style -- "${files[@]}"
