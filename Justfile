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
lint:
    bash -n $(git ls-files *.sh *.bash)
    echo "lint ok"
