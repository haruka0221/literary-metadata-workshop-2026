#!/usr/bin/env python3
"""Build Work-by-decade, language, and quality tables from OL Editions."""

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

csv.field_size_limit(sys.maxsize)

LANG_MISSING = "__MISSING__"
YEAR_UNKNOWN = "UNKNOWN"


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rows(path):
    with path.open(encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t")


def write_tsv(path, fields, records):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(records)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--details", required=True, type=Path)
    ap.add_argument("--links", required=True, type=Path)
    ap.add_argument("--summary", required=True, type=Path)
    ap.add_argument("--dest", required=True, type=Path)
    ap.add_argument("--review-min-year", type=int, default=1880)
    ap.add_argument("--review-max-year", type=int, default=2026)
    args = ap.parse_args()

    if args.review_min_year > args.review_max_year:
        ap.error("Invalid year review range")

    paths = [args.details.resolve(), args.links.resolve(),
             args.summary.resolve()]
    details_path, links_path, summary_path = paths

    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)

    dest = args.dest.resolve()
    partial = dest.parent / f".{dest.name}.incomplete"

    if dest.exists() or partial.exists():
        raise FileExistsError("Output or incomplete directory exists")

    summary = {}
    for row in rows(summary_path):
        wid = row["source_ol_work_id"]
        if wid in summary:
            raise ValueError(f"Duplicate summary Work: {wid}")
        summary[wid] = int(row["edition_count"])

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial.mkdir()

    db = partial / "_working_join.sqlite3"
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("""
        CREATE TABLE edition (
            eid TEXT PRIMARY KEY,
            decade TEXT NOT NULL,
            year_flag TEXT NOT NULL,
            languages TEXT NOT NULL,
            multi_language INTEGER NOT NULL,
            duplicate_language INTEGER NOT NULL,
            missing_language INTEGER NOT NULL,
            incomplete_date INTEGER NOT NULL,
            und_language INTEGER NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE link (
            eid TEXT NOT NULL REFERENCES edition(eid),
            wid TEXT NOT NULL,
            is_target INTEGER NOT NULL,
            PRIMARY KEY(eid, wid)
        )
    """)

    detail_count = 0

    with con:
        for row in rows(details_path):
            eid = row["edition_key"]
            year_raw = row["publish_year"]
            status = row["publish_year_parse_status"]

            if year_raw:
                year = int(year_raw)
                decade = str((year // 10) * 10)

                if year < args.review_min_year:
                    year_flag = "BEFORE_REVIEW_MIN"
                elif year > args.review_max_year:
                    year_flag = "AFTER_REVIEW_MAX"
                else:
                    year_flag = "OBSERVED"
            else:
                decade = YEAR_UNKNOWN
                year_flag = "UNKNOWN"

            raw_languages = json.loads(row["languages_json"])

            if raw_languages is None:
                raw_languages = []

            if not isinstance(raw_languages, list):
                raise ValueError(f"Invalid languages: {eid}")

            codes = []

            for item in raw_languages:
                if not isinstance(item, dict):
                    raise ValueError(f"Invalid language item: {eid}")

                key = item.get("key")
                if not isinstance(key, str):
                    raise ValueError(f"Invalid language key: {eid}")

                match = re.fullmatch(
                    r"/languages/([A-Za-z0-9_-]+)", key
                )
                if not match:
                    raise ValueError(f"Unexpected language key: {key}")

                codes.append(match.group(1))

            unique_codes = sorted(set(codes))
            missing_language = not unique_codes

            if missing_language:
                unique_codes = [LANG_MISSING]

            con.execute(
                "INSERT INTO edition VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    eid, decade, year_flag,
                    json.dumps(unique_codes),
                    int(len(unique_codes) > 1 and not missing_language),
                    int(len(codes) != len(set(codes))),
                    int(missing_language),
                    int(status == "YEAR_WITH_INVALID_DATE_COMPONENTS"),
                    int("und" in unique_codes),
                ),
            )
            detail_count += 1

    link_count = 0
    target_link_count = 0

    with con:
        for row in rows(links_path):
            eid = row["edition_key"]
            wid = row["source_ol_work_id"]
            raw_flag = row["is_extraction_target"]

            if raw_flag not in ("0", "1"):
                raise ValueError(f"Invalid target flag: {eid}")

            flag = int(raw_flag)

            if flag and wid not in summary:
                raise ValueError(f"Unknown target Work: {wid}")

            con.execute(
                "INSERT INTO link VALUES (?,?,?)",
                (eid, wid, flag),
            )

            link_count += 1
            target_link_count += flag

    decade_counts = Counter()
    language_counts = Counter()
    work_counts = Counter()
    quality = defaultdict(Counter)

    query = """
        SELECT l.wid, e.decade, e.year_flag, e.languages,
               e.multi_language, e.duplicate_language,
               e.missing_language, e.incomplete_date, e.und_language
        FROM link AS l
        JOIN edition AS e ON e.eid = l.eid
        WHERE l.is_target = 1
        ORDER BY l.wid, l.eid
    """

    for (wid, decade, year_flag, language_json,
         multi, duplicate, missing, incomplete, und) in con.execute(query):

        work_counts[wid] += 1
        decade_counts[(wid, decade, year_flag)] += 1

        codes = json.loads(language_json)
        for code in codes:
            language_counts[(wid, code)] += 1

        q = quality[wid]

        if year_flag == "UNKNOWN":
            q["year_unknown"] += 1
        elif year_flag == "BEFORE_REVIEW_MIN":
            q["year_before_review_min"] += 1
        elif year_flag == "AFTER_REVIEW_MAX":
            q["year_after_review_max"] += 1

        q["language_missing"] += missing
        q["multiple_distinct_languages"] += multi
        q["duplicate_language_tags"] += duplicate
        q["incomplete_date"] += incomplete
        q["explicit_und_language"] += und

    if detail_count != con.execute(
        "SELECT COUNT(*) FROM edition"
    ).fetchone()[0]:
        raise AssertionError("Edition count mismatch")

    represented = con.execute("""
        SELECT COUNT(DISTINCT eid)
        FROM link WHERE is_target = 1
    """).fetchone()[0]

    if represented != detail_count:
        raise AssertionError("Not all Editions have a target Work link")

    for wid, count in summary.items():
        if work_counts[wid] != count:
            raise AssertionError(
                f"Work count mismatch: {wid}: "
                f"{work_counts[wid]} != {count}"
            )

    if sum(work_counts.values()) != target_link_count:
        raise AssertionError("Target link count mismatch")

    con.close()
    db.unlink()

    write_tsv(
        partial / "work_edition_by_decade_v1.tsv",
        ["source_ol_work_id", "decade_start_year",
         "year_review_category", "edition_count"],
        [
            (wid, decade, flag, count)
            for (wid, decade, flag), count
            in sorted(decade_counts.items())
        ],
    )

    write_tsv(
        partial / "work_edition_by_language_v1.tsv",
        ["source_ol_work_id", "language_code", "edition_count"],
        [
            (wid, code, count)
            for (wid, code), count
            in sorted(language_counts.items())
        ],
    )

    quality_fields = [
        "year_unknown",
        "year_before_review_min",
        "year_after_review_max",
        "language_missing",
        "multiple_distinct_languages",
        "duplicate_language_tags",
        "incomplete_date",
        "explicit_und_language",
    ]

    write_tsv(
        partial / "work_edition_quality_v1.tsv",
        ["source_ol_work_id", "edition_count"] + quality_fields,
        [
            (wid, summary[wid]) +
            tuple(quality[wid][field] for field in quality_fields)
            for wid in sorted(summary)
        ],
    )

    outputs = {}
    for name in (
        "work_edition_by_decade_v1.tsv",
        "work_edition_by_language_v1.tsv",
        "work_edition_quality_v1.tsv",
    ):
        p = partial / name
        outputs[name] = {
            "bytes": p.stat().st_size,
            "sha256": sha256(p),
        }

    manifest = {
        "status": "LOCAL_VALIDATION_NOT_PUBLISHED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {
            str(p): sha256(p) for p in paths
        },
        "builder_sha256": sha256(Path(__file__).resolve()),
        "unique_editions": detail_count,
        "all_work_links": link_count,
        "target_work_links": target_link_count,
        "target_work_count": len(summary),
        "review_min_year": args.review_min_year,
        "review_max_year": args.review_max_year,
        "year_outliers_retained": True,
        "missing_language_code": LANG_MISSING,
        "multilingual_counting": "ONE_PER_DISTINCT_LANGUAGE_PER_EDITION",
        "outputs": outputs,
        "interpretation": (
            "Open Library Edition metadata observations; "
            "not verified historical publication totals."
        ),
    }

    (partial / "manifest_v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    partial.rename(dest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
