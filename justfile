# Einfacher Task-Runner: https://github.com/casey/just

set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

smoke-sichter:
    bash scripts/ci-smoke-sichter.sh

dev-sichter:
    # API im Vordergrund starten (Strg-C beendet)
    PORT=5055 HOST=127.0.0.1 bin/uvicorn-app
