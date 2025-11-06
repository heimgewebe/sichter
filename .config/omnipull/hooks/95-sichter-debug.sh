#!/usr/bin/env bash
set -euo pipefail
ts(){ date -Is; }
LOG="$HOME/sichter/logs/omnipull-sichter.log"
echo "[debug-hook] =====================================================" | tee -a "$LOG"
echo "[debug-hook] start @ $(ts)" | tee -a "$LOG"
echo "[debug-hook] env:
  USER=$USER  HOSTNAME=$(hostname)
  PWD=$(pwd)
  GH_AUTH=$(command -v gh >/dev/null 2>&1 && echo ok || echo miss)
  OLLAMA=$(pgrep -x ollama >/dev/null 2>&1 && echo ok || echo miss)
" | tee -a "$LOG"
echo "[debug-hook] done  @ $(ts)" | tee -a "$LOG"
echo "[debug-hook] =====================================================" | tee -a "$LOG"
