#!/usr/bin/env bash
set -euo pipefail

policy_print() { "$HOME/sichter/bin/sichter-env" --print 2>/dev/null || true; }

menu() {
	whiptail --title "Sichter-Dashboard" --menu "Aktion wählen:" 20 60 10 \
		1 "Autopilot-Status anzeigen" \
		2 "Autopilot neu starten" \
		3 "Ollama-Modelle prüfen" \
		4 "Worker-Logs anzeigen" \
		5 "Fix-PRs jetzt anstoßen" \
		6 "Policy anzeigen" \
		7 "Beenden" 3>&1 1>&2 2>&3
}
while true; do
	choice=$(menu) || exit 0
	case "$choice" in
	1) systemctl --user status hauski-autopilot.service | less ;;
	2) systemctl --user restart hauski-autopilot.service ;;
	3) ollama list | less ;;
	4) less +F "$HOME/sichter/logs/autopilot.log" ;;
	5) "$HOME/sichter/hooks/post-run" ;;
	6) policy_print | whiptail --title "Sichter-Policy" --msgbox "$(cat -)" 10 70 ;;
	*) break ;;
	esac
done
