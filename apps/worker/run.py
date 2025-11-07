# apps/worker/run.py
import subprocess, json, time, os, shutil
from pathlib import Path
from datetime import datetime

HOME  = Path.home()
STATE = HOME/".local/state/sichter"
QUEUE = STATE/"queue"
EVENTS= STATE/"events"
LOGS  = STATE/"logs"
for p in (QUEUE, EVENTS, LOGS): p.mkdir(parents=True, exist_ok=True)

def log(line: str, file_name="worker.log"):
    ts = datetime.now().isoformat()
    out = f"[{ts}] {line}"
    print(out, flush=True)
    with (EVENTS/file_name).open("a") as f:
        f.write(out + "\n")

def run(cmd, cwd=None, check=False):
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)

def repos_for_mode(org:str, mode:str, single_repo:str|None):
    base = HOME/"repos"
    if single_repo: return [single_repo]
    if mode == "all":
        # prefer local dirs; fallback to gh
        if base.exists():
            return [p.name for p in base.iterdir() if (p/".git").exists()]
        try:
            r = run(["gh","repo","list",org,"--limit","100","--json","name","-q",".[].name"])
            return [x for x in r.stdout.splitlines() if x.strip()]
        except Exception: return []
    else:
        # "changed": simplest heuristic = all local repos
        if base.exists():
            return [p.name for p in base.iterdir() if (p/".git").exists()]
        return []

def fresh_branch(repo_dir:Path):
    run(["git","fetch","origin","--prune","--tags"], cwd=repo_dir)
    r = run(["git","switch","--detach","origin/main"], cwd=repo_dir)
    if r.returncode != 0:
        run(["git","checkout","--detach","origin/main"], cwd=repo_dir)
    br = "sichter/autofix-"+datetime.now().strftime("%Y%m%d-%H%M%S")
    r = run(["git","switch","-C",br], cwd=repo_dir)
    if r.returncode != 0:
        run(["git","checkout","-B",br], cwd=repo_dir)
    return br

def shellcheck(repo_dir:Path):
    if shutil.which("shellcheck"):
        run(["bash","-lc",
             r"find . -type f -name '*.sh' -not -path './.venv/*' -not -path './venv/*' -not -path './node_modules/*' -print0 | xargs -0 -r shellcheck -x || true"],
            cwd=repo_dir)

def yamllint(repo_dir:Path):
    if shutil.which("yamllint"):
        run(["bash","-lc",
             r"find . -type f \( -name '*.yml' -o -name '*.yaml' \) -not -path './.venv/*' -not -path './venv/*' -not -path './node_modules/*' -print0 | xargs -0 -r yamllint -s || true"],
            cwd=repo_dir)

def commit_if_changes(repo_dir:Path):
    run(["git","add","-A"], cwd=repo_dir)
    r = run(["git","diff","--cached","--quiet"], cwd=repo_dir)
    if r.returncode != 0:
        run(["git","commit","-m","hauski: autofix"], cwd=repo_dir)
        return True
    return False

def create_or_update_pr(repo:str, repo_dir:Path, br:str, auto_pr:bool):
    if not auto_pr:
        log(f"COMMIT {repo:<22} {br} (auto_pr=off)", "pr.log");
        return
    run(["git","push","--set-upstream","origin",br,"--force-with-lease"], cwd=repo_dir)
    # try view; if none → create
    v = run(["gh","pr","view",br,"--json","url","-q",".url"], cwd=repo_dir)
    if v.returncode != 0 or not v.stdout.strip():
        run(["gh","pr","create","--base","main","--fill","--title",f"Sichter: auto PR ({repo})",
             "--label","sichter","--label","automation"], cwd=repo_dir)
        v = run(["gh","pr","view",br,"--json","url","-q",".url"], cwd=repo_dir)
    url = v.stdout.strip() if v.stdout else "n/a"
    log(f"CREATE  {repo:<22} {br} -> {url}", "pr.log")

def handle_job(job:dict):
    jtype = job.get("type")
    mode  = job.get("mode","changed")
    org   = job.get("org","heimgewebe")
    one   = job.get("repo")
    auto  = bool(job.get("auto_pr", True))

    log(f"JOB {jtype} mode={mode} org={org} repo={one}")
    repos = repos_for_mode(org, "all" if jtype=="ScanAll" else mode, one)
    if not repos:
        log(f"Keine Ziel-Repos (mode={mode})")
        return

    for r in repos:
        repo_dir = HOME/"repos"/r
        if not (repo_dir/".git").exists():
            run(["gh","repo","clone",f"{org}/{r}",str(repo_dir)])
            if not (repo_dir/".git").exists():
                log(f"skip {r} (clone failed)")
                continue

        br = fresh_branch(repo_dir)
        # (MVP) Analyser:
        shellcheck(repo_dir)
        yamllint(repo_dir)
        changed = commit_if_changes(repo_dir)
        if changed:
            create_or_update_pr(r, repo_dir, br, auto)
        else:
            log(f"NOCHANGE {r:<22} {br}", "pr.log")

def main():
    log("worker start")
    while True:
        for jobfile in sorted(QUEUE.glob("*.json")):
            try:
                job = json.loads(jobfile.read_text())
                handle_job(job)
            except Exception as e:
                log(f"error processing {jobfile.name}: {e}")
            finally:
                try: jobfile.unlink()
                except: pass
        time.sleep(2)

if __name__ == "__main__":
    main()
