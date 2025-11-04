#!/usr/bin/env bash
set -euo pipefail
ROOT="$HOME/sichter"
LOG="$ROOT/logs/bootstrap.log"
mkdir -p "$ROOT/logs"
echo "[BOOTSTRAP] $(date)" >>"$LOG"

if ! pgrep -f "ollama serve" >/dev/null; then
	nohup ollama serve >/dev/null 2>&1 &
	echo "Ollama gestartet" >>"$LOG"
fi

MODEL="${HAUSKI_OLLAMA_MODEL:-qwen2.5-coder:7b}"
if ! ollama list | grep -q "$MODEL"; then
	echo "Lade Modell $MODEL ..." >>"$LOG"
	ollama pull "$MODEL" >>"$LOG" 2>&1
fi

for w in hauski-watch hauski-work hauski-pr-watch; do
	path="$ROOT/bin/$w"
	[ -x "$path" ] || {
		printf '#!/usr/bin/env bash\nsleep infinity\n' >"$path"
		chmod +x "$path"
		echo "Stub $w erzeugt" >>"$LOG"
	}
done

systemctl --user enable --now hauski-autopilot.service
echo "Autopilot aktiv." >>"$LOG"
