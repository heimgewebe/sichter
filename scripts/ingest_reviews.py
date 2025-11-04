#!/usr/bin/env python3
"""Export Hauski review markdown files into JSONL insights for semantAH."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


def parse_review_md(text: str) -> dict[str, object]:
    """Extract structured fields from a Hauski review markdown block."""

    def match(pattern: str, default: str = "") -> str:
        match_obj = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        return match_obj.group(1).strip() if match_obj else default

    score_str = match(r"^HAUSKI_SCORE:\s*([0-9]+)")
    verdict = match(r"^Verdict:\s*(.+)$", "unknown")
    pr_ref = match(r"^PR:\s*(.+)$", "")
    tags = sorted({tag.lower() for tag in re.findall(r"#([A-Za-z0-9_\-]+)", text)})

    score = int(score_str) if score_str.isdigit() else 0
    return {
        "score": score,
        "verdict": verdict,
        "pr": pr_ref,
        "tags": tags,
    }


def iter_reviews(index: Path, repo_filter: str | None) -> list[tuple[str, Path]]:
    data = json.loads(index.read_text(encoding="utf-8"))
    entries: list[tuple[str, Path]] = []
    if isinstance(data, dict):
        for repo, meta in data.items():
            if repo_filter and repo != repo_filter:
                continue
            latest = meta.get("path") or meta.get("latest")
            if latest:
                entries.append((repo, Path(latest).expanduser()))
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            repo = item.get("repo") or "unknown"
            if repo_filter and repo != repo_filter:
                continue
            path_value = item.get("path")
            if path_value:
                entries.append((repo, Path(path_value).expanduser()))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--review-root",
        default=os.path.expanduser("~/sichter/review"),
        help="Directory that holds review reports and index.json",
    )
    parser.add_argument(
        "--out",
        default=os.path.expanduser("~/.gewebe/insights/reviews.jsonl"),
        help="Target JSONL file (append mode)",
    )
    parser.add_argument("--repo", default=None, help="Optional repo filter")
    args = parser.parse_args()

    review_root = Path(args.review_root)
    index_file = review_root / "index.json"
    if not index_file.exists():
        print(f"index.json not found: {index_file}", file=sys.stderr)
        return 0

    out_path = Path(args.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        fallback = Path.home() / "sichter" / "insights" / out_path.name
        fallback.parent.mkdir(parents=True, exist_ok=True)
        print(
            f"insufficient permission for {out_path.parent}, writing to {fallback} instead",
            file=sys.stderr,
        )
        out_path = fallback

    entries = iter_reviews(index_file, args.repo)
    if not entries:
        print("no review entries found", file=sys.stderr)
        return 0

    written = 0
    with out_path.open("a", encoding="utf-8") as handle:
        for repo, review_path in entries:
            if not review_path.exists():
                continue
            text = review_path.read_text(encoding="utf-8", errors="ignore")
            parsed = parse_review_md(text)
            insight = {
                "type": "review.insight",
                "repo": repo,
                "source": "hauski",
                "file": str(review_path),
                "score": parsed["score"],
                "verdict": parsed["verdict"],
                "pr": parsed["pr"],
                "tags": parsed["tags"],
            }
            handle.write(json.dumps(insight, ensure_ascii=False) + "\n")
            written += 1

    print(f"wrote {written} insights -> {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
