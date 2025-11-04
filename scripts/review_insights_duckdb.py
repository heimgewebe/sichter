#!/usr/bin/env python3
"""Quick DuckDB queries over Hauski review parquet datasets."""
from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path


def run_query(parquet_glob: str, top_n: int, repo: str | None) -> None:
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "duckdb is required. Install via `pip install --user duckdb`."
        ) from exc

    con = duckdb.connect()

    repo_filter_clause = ""
    if repo:
        safe_repo = repo.replace("'", "''")
        repo_filter_clause = f"AND repo = '{safe_repo}'"

    base_query = f"""
        WITH exploded AS (
            SELECT
                repo,
                DATE_TRUNC('month', CAST(ingested_at AS TIMESTAMP)) AS month,
                UNNEST(tags) AS tag,
                score
            FROM read_parquet('{parquet_glob}')
        ),
        stats AS (
            SELECT
                repo,
                month,
                tag,
                COUNT(*) AS tag_count,
                AVG(score) AS avg_score,
                ROW_NUMBER() OVER (
                    PARTITION BY repo, month
                    ORDER BY COUNT(*) DESC, tag
                ) AS rk
            FROM exploded
            WHERE 1=1
              {repo_filter_clause}
            GROUP BY repo, month, tag
        )
        SELECT
            repo,
            strftime(month, '%Y-%m') AS month,
            tag,
            tag_count,
            ROUND(avg_score, 2) AS avg_score
        FROM stats
        WHERE rk <= {top_n}
        ORDER BY repo, month, tag_count DESC, tag;
    """

    result = con.execute(base_query)

    rows = result.fetchall()
    if not rows:
        print("no rows matched your query", file=sys.stderr)
        return

    headers = [desc[0] for desc in result.description]
    widths = [max(len(str(value)) for value in [header] + [row[idx] for row in rows]) for idx, header in enumerate(headers)]
    fmt = "  ".join(f"{{:{w}}}" for w in widths)
    print(fmt.format(*headers))
    for row in rows:
        print(fmt.format(*row))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parquet-glob",
        default=str(Path.home() / "sichter" / "insights" / "parquet" / "*.parquet"),
        help="Glob pattern for parquet dataset (default: ~/sichter/insights/parquet/*.parquet)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="Top N tags per repo and month (default: 5)",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Optional repository filter",
    )
    args = parser.parse_args(argv)

    matches = glob.glob(args.parquet_glob)
    if not matches:
        print(f"no parquet files found for pattern: {args.parquet_glob}", file=sys.stderr)
        return 1

    run_query(args.parquet_glob, args.top, args.repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
