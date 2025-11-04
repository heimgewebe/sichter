#!/usr/bin/env bash
set -euo pipefail
ENV="$HOME/sichter/autostart.env"
POST="$HOME/sichter/hooks/post-run"

get_policy() {
  p="periodic"
  [ -f "$ENV" ] && p="$(grep -E '^SICHTER_RUN_POLICY=' "$ENV" | cut -d= -f2- || echo periodic)"
  echo "${p:-periodic}"
}
set_policy() {
  pol="$1"
  grep -q '^SICHTER_RUN_POLICY=' "$ENV" \
    && sed -i "s|^SICHTER_RUN_POLICY=.*|SICHTER_RUN_POLICY=$pol|" "$ENV" \
    || echo "SICHTER_RUN_POLICY=$pol" >> "$ENV"
  echo "⚙️ Policy = $pol"
}

menu() {
  cur="$(get_policy)"
  whiptail --title "Sichter-Dashboard" --menu "Aktion wählen (Policy: $cur):" 22 80 12 \
    1 "Autopilot-Status anzeigen" \
    2 "Autopilot START (periodic)" \
    3 "Autopilot STOPPEN" \
    4 "Policy: periodic (alle 5 Min laufen)" \
    5 "Policy: after_omnipull (nur nach omnipull laufen)" \
    6 "Jetzt sofort laufen (post-run)" \
    7 "Ollama-Modelle anzeigen" \
    8 "Logs anzeigen (autopilot.log)" \
     9 "Reports bereinigen" \
     10 "Beenden" 3>&1 1>&2 2>&3
}
while true; do
  choice=$(menu) || exit 0
  case "$choice" in
    9) "$HOME/sichter/bin/sichter-sanitize-reports" >/dev/null 2>&1 || true; \
       whiptail --msgbox "Reports bereinigt." 8 40 ;;
    1) systemctl --user status hauski-autopilot.service | less ;;
    2) set_policy periodic; systemctl --user enable --now hauski-autopilot.service ;;
    3) systemctl --user stop hauski-autopilot.service ;;
    4) set_policy periodic ;;
    5) set_policy after_omnipull; systemctl --user disable --now hauski-autopilot.service || true ;;
    6) [ -x "$POST" ] && "$POST" || echo "post-run Hook fehlt" ;;
    7) ollama list | less ;;
    8) less +F "$HOME/sichter/logs/autopilot.log" ;;
    10) exit 0 ;;
  esac
done
