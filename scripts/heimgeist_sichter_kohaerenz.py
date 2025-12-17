#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
heimgeist.sichter.kohaerenz
============================

Kohärenz-Scanner für repoLens JSON-Snapshots.
Er erzeugt Befunde aus einem Snapshot, ohne ins Live-Repo zu schauen.

Philosophie: "Befund statt Befehl".
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Iterable, Tuple


# -----------------------------
# Models
# -----------------------------

@dataclass
class Finding:
    severity: str  # info | warn | crit
    code: str
    title: str
    detail: str
    repo: Optional[str] = None


@dataclass
class Report:
    generated_at: str
    agent: str
    input_path: str
    meta: Dict[str, Any]
    scope: str
    coverage_pct: Optional[float]
    files_total: Optional[int]
    repos: List[str]
    repo_stats: Dict[str, Any]
    findings: List[Finding]
    uncertainty: Dict[str, Any]


# -----------------------------
# Helpers
# -----------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _safe_get(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _list_files(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    files = doc.get("files")
    if isinstance(files, list):
        return [x for x in files if isinstance(x, dict)]
    return []


def _iter_paths(files: List[Dict[str, Any]]) -> Iterable[Tuple[str, str]]:
    """
    Yields (repo, path) pairs. repo may be "" if unknown.
    """
    for f in files:
        p = f.get("path")
        r = f.get("repo")
        if isinstance(p, str):
            yield (r if isinstance(r, str) and r else "", p)


def _repos_from_doc(doc: Dict[str, Any], files: List[Dict[str, Any]]) -> List[str]:
    src = _safe_get(doc, "meta", "source_repos", default=[])
    repos = set()
    if isinstance(src, list):
        for x in src:
            if isinstance(x, str) and x:
                repos.add(x)
    for r, _ in _iter_paths(files):
        if r:
            repos.add(r)
    return sorted(repos)


def _has_prefix(paths: List[str], prefix: str) -> bool:
    pref = prefix.rstrip("/") + "/"
    return any(p.startswith(pref) for p in paths)


def _has_any_file(paths: List[str], names: List[str]) -> bool:
    s = set(paths)
    return any(n in s for n in names)


# -----------------------------
# Core checks
# -----------------------------

def _meta_sanity(doc: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []

    contract = _safe_get(doc, "meta", "contract")
    ver = _safe_get(doc, "meta", "contract_version")
    spec = _safe_get(doc, "meta", "spec_version")
    profile = _safe_get(doc, "meta", "profile")
    coverage = _safe_get(doc, "coverage", "coverage_pct")
    filters = _safe_get(doc, "meta", "filters", default={})
    content_policy = filters.get("content_policy") if isinstance(filters, dict) else None

    if contract != "repolens-agent" or ver != "v1":
        findings.append(Finding(
            severity="warn",
            code="HG-SICHTER-010",
            title="Unerwarteter Snapshot-Contract",
            detail=f"Erwartet repolens-agent/v1. Gefunden: {contract}/{ver}. Befunde sind nur eingeschränkt interpretierbar.",
        ))

    if isinstance(spec, str) and spec != "2.4":
        findings.append(Finding(
            severity="info",
            code="HG-SICHTER-011",
            title="Spec-Version ist nicht 2.4",
            detail=f"spec_version={spec!r}. Der Sichter ist auf 2.4 optimiert; Details können abweichen.",
        ))

    if isinstance(coverage, (int, float)) and coverage < 95.0:
        findings.append(Finding(
            severity="warn",
            code="HG-SICHTER-012",
            title="Coverage < 95%",
            detail=f"coverage_pct={coverage}. Hohe Chance auf blinde Flecken. Befunde sind eher Tendenzen als Aussagen.",
        ))

    if isinstance(filters, dict):
        pf = filters.get("path_filter") or ""
        ef = filters.get("ext_filter") or ""
        if isinstance(pf, str) and pf.strip():
            findings.append(Finding(
                severity="info",
                code="HG-SICHTER-013",
                title="Path-Filter aktiv",
                detail=f"path_filter={pf!r}. Struktur-Marker können außerhalb des Scope liegen.",
            ))
        if isinstance(ef, str) and ef.strip():
            findings.append(Finding(
                severity="info",
                code="HG-SICHTER-014",
                title="Extension-Filter aktiv",
                detail=f"ext_filter={ef!r}. Struktur-Befunde sind ggf. verzerrt.",
            ))

        if content_policy == "code-only":
            findings.append(Finding(
                severity="info",
                code="HG-SICHTER-015",
                title="content_policy=code-only",
                detail="Code-only ist gut für Agenten-Parsing, aber kann Dokumentations-/Policy-Signale ausblenden.",
            ))

    if isinstance(profile, str) and profile.lower() in ("dev", "min"):
        findings.append(Finding(
            severity="info",
            code="HG-SICHTER-016",
            title="Profil ist nicht maximal",
            detail=f"profile={profile!r}. Für Kohärenz-Checks ist max oft sinnvoller (weniger blinde Flecken).",
        ))

    return findings


def _duplicates_within_repo(files: List[Dict[str, Any]]) -> Tuple[List[Tuple[str, str]], bool]:
    """
    Returns (duplicates, has_unknown_repos).
    has_unknown_repos is True if any file has missing/empty repo field.
    """
    seen = set()
    dups = set()
    has_unknown = False
    for repo, path in _iter_paths(files):
        if not repo:
            has_unknown = True
        key = (repo, path)
        if key in seen:
            dups.add(key)
        seen.add(key)
    return sorted(dups), has_unknown


def _repo_marker_findings(repo: str, repo_paths: List[str]) -> List[Finding]:
    findings: List[Finding] = []

    has_ai = _has_any_file(repo_paths, [".ai-context.yml", "ai-context.yml"])
    has_wgx = _has_prefix(repo_paths, ".wgx")
    has_contracts = _has_prefix(repo_paths, "contracts")
    has_docs = _has_prefix(repo_paths, "docs") or _has_prefix(repo_paths, "doc")
    has_workflows = _has_prefix(repo_paths, ".github/workflows")

    if not has_ai:
        findings.append(Finding(
            severity="warn",
            code="HG-SICHTER-101",
            title="Kein ai-context sichtbar",
            detail="Weder .ai-context.yml noch ai-context.yml gefunden. Kann echtes Fehlen sein oder Filter-Effekt.",
            repo=repo or None,
        ))

    if not has_wgx:
        findings.append(Finding(
            severity="warn",
            code="HG-SICHTER-102",
            title="Kein .wgx/ sichtbar",
            detail="WGX-Motorik fehlt im Snapshot. Für Fleet-Repos wäre das ein Drift-Signal.",
            repo=repo or None,
        ))

    if not has_workflows:
        findings.append(Finding(
            severity="info",
            code="HG-SICHTER-103",
            title="Keine Workflows sichtbar",
            detail="Kein CI sichtbar. Kann Absicht sein; erhöht aber Integrationsrisiko.",
            repo=repo or None,
        ))

    if not has_contracts:
        findings.append(Finding(
            severity="info",
            code="HG-SICHTER-104",
            title="Kein contracts/ sichtbar",
            detail="Nicht jedes Repo braucht Contracts. Für zentrale Repos kann es semantische Entkopplung anzeigen.",
            repo=repo or None,
        ))

    if not has_docs:
        findings.append(Finding(
            severity="info",
            code="HG-SICHTER-105",
            title="Keine docs/ sichtbar",
            detail="Dokumentation fehlt im Snapshot oder wurde gefiltert. Risiko: Wissen wird implizit.",
            repo=repo or None,
        ))

    return findings


def _uncertainty(doc: Dict[str, Any]) -> Dict[str, Any]:
    coverage = _safe_get(doc, "coverage", "coverage_pct")
    filters = _safe_get(doc, "meta", "filters", default={})
    causes: List[str] = []
    score = 0.18

    if isinstance(coverage, (int, float)) and coverage < 100.0:
        score += 0.10
        causes.append("Coverage < 100%: Snapshot ist unvollständig (blinde Flecken).")

    if isinstance(filters, dict) and (filters.get("path_filter") or filters.get("ext_filter")):
        score += 0.08
        causes.append("Filter aktiv: Struktur-Befunde können verzerrt sein.")

    if isinstance(filters, dict) and filters.get("content_policy") == "code-only":
        score += 0.06
        causes.append("content_policy=code-only: Kontextsignale aus Doku/Policies können fehlen.")

    score = max(0.0, min(0.95, score))
    return {
        "uncertainty_score": score,
        "causes": causes or ["Keine dominanten Ungewissheits-Treiber erkannt (aber Snapshot bleibt Snapshot)."],
        "note": "Ungewissheit ist hier produktiv: Sie verhindert, dass Snapshot-Befunde als Live-Wahrheit missverstanden werden.",
    }


def build_report(doc: Dict[str, Any], input_path: Path) -> Report:
    files = _list_files(doc)
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    scope = doc.get("scope") if isinstance(doc.get("scope"), str) else ""
    coverage = _safe_get(doc, "coverage", "coverage_pct")
    files_total = _safe_get(doc, "meta", "total_files")

    repos = _repos_from_doc(doc, files)

    repo_to_paths: Dict[str, List[str]] = {r: [] for r in repos}
    repo_to_count: Dict[str, int] = {r: 0 for r in repos}
    for r, p in _iter_paths(files):
        rr = r if r else ""
        if rr not in repo_to_paths:
            repo_to_paths[rr] = []
            repo_to_count[rr] = 0
        repo_to_paths[rr].append(p)
        repo_to_count[rr] += 1

    findings: List[Finding] = []
    findings.extend(_meta_sanity(doc))

    dups, has_unknown_repos = _duplicates_within_repo(files)
    if dups:
        show = ", ".join([f"{r}:{p}" for (r, p) in dups[:40]])
        # If repo info is unknown, we can't be certain duplicates are within same repo
        # so downgrade to warn instead of crit
        severity = "warn" if has_unknown_repos else "crit"
        title_suffix = " (Repo-Zuordnung teilweise unbekannt)" if has_unknown_repos else ""
        detail_suffix = " Hinweis: Repo-Zuordnung fehlt, daher unsicher ob echte Duplikate." if has_unknown_repos else ""
        findings.append(Finding(
            severity=severity,
            code="HG-SICHTER-020",
            title="Doppelte Pfade" + title_suffix,
            detail=show + (" …" if len(dups) > 40 else "") + detail_suffix,
        ))

    for r in sorted(repo_to_paths.keys()):
        findings.extend(_repo_marker_findings(r, repo_to_paths[r]))

    repo_stats = {
        "repos": sorted(repo_to_paths.keys()),
        "file_counts": repo_to_count,
        "markers": {
            r: {
                "ai_context": _has_any_file(repo_to_paths[r], [".ai-context.yml", "ai-context.yml"]),
                "wgx": _has_prefix(repo_to_paths[r], ".wgx"),
                "contracts": _has_prefix(repo_to_paths[r], "contracts"),
                "docs": _has_prefix(repo_to_paths[r], "docs") or _has_prefix(repo_to_paths[r], "doc"),
                "workflows": _has_prefix(repo_to_paths[r], ".github/workflows"),
            }
            for r in repo_to_paths.keys()
        },
    }

    return Report(
        generated_at=_now_iso(),
        agent="heimgeist.sichter.kohaerenz",
        input_path=str(input_path),
        meta=meta,
        scope=scope,
        coverage_pct=coverage if isinstance(coverage, (int, float)) else None,
        files_total=files_total if isinstance(files_total, int) else None,
        repos=sorted(repo_to_paths.keys()),
        repo_stats=repo_stats,
        findings=findings,
        uncertainty=_uncertainty(doc),
    )


def render_markdown(rep: Report) -> str:
    lines: List[str] = []
    lines.append(f"# {rep.agent}")
    lines.append("")
    lines.append(f"- generated_at: `{rep.generated_at}`")
    lines.append(f"- input: `{rep.input_path}`")
    if rep.scope:
        lines.append(f"- scope: `{rep.scope}`")
    if rep.coverage_pct is not None:
        lines.append(f"- coverage_pct: `{rep.coverage_pct}`")
    if rep.files_total is not None:
        lines.append(f"- total_files(meta): `{rep.files_total}`")
    lines.append(f"- repos: `{', '.join(rep.repos) if rep.repos else '(unknown)'}`")
    lines.append("")

    lines.append("## Repo-Matrix (Marker)")
    markers = rep.repo_stats.get("markers", {})
    counts = rep.repo_stats.get("file_counts", {})
    if not markers:
        lines.append("_Keine Repo-Infos._")
        lines.append("")
    else:
        lines.append("| repo | ai-context | .wgx | contracts | docs | workflows | files |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        def yn(v: bool) -> str:
            return "✓" if v else "—"
        for r in sorted(markers.keys()):
            m = markers[r]
            lines.append(
                f"| `{r or '(unknown)'}` | {yn(m['ai_context'])} | {yn(m['wgx'])} | {yn(m['contracts'])} | {yn(m['docs'])} | {yn(m['workflows'])} | {counts.get(r, 0)} |"
            )
        lines.append("")

    def bucket(sev: str) -> List[Finding]:
        return [f for f in rep.findings if f.severity == sev]

    for sev, title in [("crit", "Kritisch"), ("warn", "Warnungen"), ("info", "Hinweise")]:
        fs = bucket(sev)
        lines.append(f"## {title} ({len(fs)})")
        if not fs:
            lines.append("_Keine._")
            lines.append("")
            continue
        for f in fs:
            where = f" (`{f.repo}`)" if f.repo else ""
            lines.append(f"- **{f.code}**{where} — {f.title}")
            lines.append(f"  - {f.detail}")
        lines.append("")

    lines.append("## Ungewissheit")
    lines.append(f"- score: `{rep.uncertainty.get('uncertainty_score')}`")
    lines.append("- Ursachen:")
    for c in rep.uncertainty.get("causes", []):
        lines.append(f"  - {c}")
    lines.append(f"- Notiz: {rep.uncertainty.get('note')}")
    lines.append("")

    lines.append("## Verdichtete Essenz")
    lines.append("Snapshot-Befunde sind Landkarten, keine Gerichtsakten. Multi-Repo ist kein Fehler – es ist nur schwerer, ehrlich zu prüfen.")
    lines.append("")
    lines.append("## Ironischer Nachsatz")
    lines.append("Wenn ein Sichter jemals „Alles perfekt“ meldet, hat er entweder gelogen oder nur `README.md` gesehen.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot_json", help="Pfad zu einem repoLens JSON Snapshot")
    ap.add_argument("--out", default="reports/heimgeist.sichter", help="Ausgabeordner")
    ap.add_argument("--json", action="store_true", help="Zusätzlich JSON-Befund schreiben")
    ap.add_argument("--emit-summary", action="store_true", help="Einzeilige JSON-Zusammenfassung nach stdout (für CI-Gates)")
    args = ap.parse_args()

    in_path = Path(args.snapshot_json).expanduser()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not in_path.exists():
        raise SystemExit(f"Input nicht gefunden: {in_path}")

    doc = _load_json(in_path)
    rep = build_report(doc, in_path.resolve())

    stem = in_path.stem
    md_path = out_dir / f"{stem}__heimgeist.sichter.kohaerenz.md"
    md_path.write_text(render_markdown(rep), encoding="utf-8")

    if args.json:
        js_path = out_dir / f"{stem}__heimgeist.sichter.kohaerenz.json"
        js_path.write_text(json.dumps(asdict(rep), ensure_ascii=False, indent=2), encoding="utf-8")

    if args.emit_summary:
        # Emit single-line JSON summary for CI gate logic
        rank = {"info": 1, "warn": 2, "crit": 3}
        max_severity = "info"
        max_rank = 1
        for f in rep.findings:
            r = rank.get(f.severity, 0)
            if r > max_rank:
                max_rank = r
                max_severity = f.severity
        summary = {
            "max_severity": max_severity,
            "total_findings": len(rep.findings),
            "crit_count": sum(1 for f in rep.findings if f.severity == "crit"),
            "warn_count": sum(1 for f in rep.findings if f.severity == "warn"),
            "info_count": sum(1 for f in rep.findings if f.severity == "info"),
        }
        print(json.dumps(summary))
    else:
        print(f"Wrote: {md_path}")
        if args.json:
            print(f"Wrote: {js_path}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
