#!/bin/bash

# logging.bash - a simple logging library for bash

log() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] [INFO]  " "$@"
}

log_err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] [ERROR] " "$@" >&2
}

log_warn() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')] [WARN]  " "$@" >&2
}
