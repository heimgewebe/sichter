# Sichter (MVP)

Autonomer Code-Reviewer + Auto-PR Engine.

## Quickstart
```bash
git clone <dieses-repo> ~/sichter
cd ~/sichter
scripts/bootstrap.sh
```
## Omnipull-Integration

Hook liegt nach `~/.config/omnipull/hooks/100-sichter-always-post.sh` und triggert nach jedem Pull:

```
~/sichter/cli/omnicheck --changed
```
## CLI
- `~/sichter/cli/omnicheck --changed|--all`
- `~/sichter/cli/sweep --changed|--all`

## Dienste
- API: `systemctl --user status sichter-api.service`
- Worker: `systemctl --user status sichter-worker.service`
- Timer: `systemctl --user list-timers | grep sichter-sweep`

## Logs
- Events/PR: `~/.local/state/sichter/events/pr.log`
- Worker:    `~/.local/state/sichter/events/worker.log`

---

## Was noch? (nice nexts)
- LLM-Analysen in `apps/worker/run.py` integrieren (Prompt + Patch-Synthese).
- Dashboard (Vite/React) hinter `/` der API bereitstellen.
- Dedupe-Logik erweitern (PR je Thema).
- Reposets/Allow-/Denylist aus `config/policy.yml` berücksichtigen.
