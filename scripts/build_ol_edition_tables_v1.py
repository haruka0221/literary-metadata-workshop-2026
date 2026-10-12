#!/usr/bin/env python3
"""Build reusable OL Edition details, links and Work summaries.

Input: JSONL records produced by the Edition dump extractor.
Output: versioned TSV tables and a provenance manifest.

The output directory is created only if it does not exist.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from parse_ol_edition_date_v1 import parse_publish_date


DETAIL_COLUMNS = [
    "edition_key", "edition_title", "publish_date_raw",
    "publish_year", "publish_year_parse_status",
    "publishers_json", "publish_places_json", "languages_json",
    "number_of_pages", "isbn_10_json", "isbn_13_json",
    "source_snapshot",
]

LINK_COLUMNS = [
    "edition_key", "source_ol_work_id",
    "work_link_ordinal", "is_extraction_target",
]

SUMMARY_COLUMNS = [
    "source_ol_work_id", "edition_count",
    "editions_with_publish_year", "editions_without_publish_year",
    "editions_with_incomplete_date",
    "earliest_observed_edition_year",
    "latest_observed_edition_year",
    "editions_with_language_metadata",
    "editions_without_language_metadata",
    "editions_with_publisher_metadata",
    "editions_without_publisher_metadata",
]


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_field(value):
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":")
    )


def get_targets(args):
    ids = list(args.target)

    if args.targets_file:
        with args.targets_file.open(encoding="utf-8-sig") as f:
            ids.extend(
                line.strip()
                for line in f
                if line.strip() and not line.lstrip().startswith("#")
            )

    if not ids:
        raise ValueError("No target Work IDs supplied")

    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate target Work IDs")

    if any(not x.startswith("OL") or not x.endswith("W")
           for x in ids):
        raise ValueError("Unexpected OL Work ID format")

    return set(ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--dest", required=True, type=Path)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--target", action="append", default=[])
    ap.add_argument("--targets-file", type=Path)
    ap.add_argument("--upstream-manifest", type=Path)
    args = ap.parse_args()

    targets = get_targets(args)
    source = args.input.expanduser().resolve()
    dest = args.dest.expanduser().resolve()
    partial = dest.parent / ("." + dest.name + ".incomplete")

    if not source.is_file():
        raise FileNotFoundError(source)
    if dest.exists() or partial.exists():
        raise FileExistsError(
            "Output or incomplete directory already exists"
        )

    upstream = None
    if args.upstream_manifest:
        upstream_path = args.upstream_manifest.resolve()
        upstream = json.loads(upstream_path.read_text())
        expected_hash = upstream.get("output_sha256")
        if expected_hash and sha256(source) != expected_hash:
            raise ValueError("Input JSONL SHA256 mismatch")

    partial.mkdir(parents=True)

    stats = defaultdict(lambda: {
        "count": 0,
        "with_year": 0,
        "without_year": 0,
        "incomplete": 0,
        "years": [],
        "with_language": 0,
        "with_publisher": 0,
    })

    seen_editions = set()
    link_count = 0
    duplicate_link_entries = 0

    details_path = partial / "edition_details_v1.tsv"
    links_path = partial / "edition_work_links_v1.tsv"

    with (
        source.open(encoding="utf-8") as inp,
        details_path.open("w", encoding="utf-8", newline="") as df,
        links_path.open("w", encoding="utf-8", newline="") as lf,
    ):
        dw = csv.writer(df, delimiter="\t", lineterminator="\n")
        lw = csv.writer(lf, delimiter="\t", lineterminator="\n")
        dw.writerow(DETAIL_COLUMNS)
        lw.writerow(LINK_COLUMNS)

        for line_number, line in enumerate(inp, 1):
            outer = json.loads(line)
            ed = outer["edition_record"]
            key = outer["edition_key"]

            if key in seen_editions:
                raise ValueError(f"Duplicate Edition: {key}")
            seen_editions.add(key)

            if ed.get("key") != key:
                raise ValueError(f"Edition key mismatch: {key}")

            raw_links = ed.get("works") or []
            if not isinstance(raw_links, list):
                raise ValueError(f"Invalid works array: {key}")

            all_keys = [
                item["key"]
                for item in raw_links
                if isinstance(item, dict)
                and isinstance(item.get("key"), str)
            ]

            if all_keys != outer["all_work_keys"]:
                raise ValueError(f"Work links mismatch: {key}")

            actual_matches = {
                k.removeprefix("/works/")
                for k in all_keys
                if k.startswith("/works/")
                and k.removeprefix("/works/") in targets
            }

            supplied_matches = set(
                outer["matched_selected_work_ids"]
            )

            if actual_matches != supplied_matches:
                raise ValueError(f"Target matches mismatch: {key}")

            if not actual_matches:
                raise ValueError(f"No target matches: {key}")

            year, date_status = parse_publish_date(
                ed.get("publish_date")
            )

            dw.writerow([
                key,
                ed.get("title"),
                ed.get("publish_date"),
                year,
                date_status,
                json_field(ed.get("publishers")),
                json_field(ed.get("publish_places")),
                json_field(ed.get("languages")),
                ed.get("number_of_pages"),
                json_field(ed.get("isbn_10")),
                json_field(ed.get("isbn_13")),
                args.snapshot,
            ])

            # Preserve every distinct source Work relationship.
            # Duplicates remain recoverable in the raw JSONL.
            unique_links = set()

            for ordinal, work_key in enumerate(all_keys):
                if work_key in unique_links:
                    duplicate_link_entries += 1
                    continue
                unique_links.add(work_key)

                wid = work_key.removeprefix("/works/")
                selected = wid in targets

                lw.writerow([
                    key, wid, ordinal, int(selected)
                ])
                link_count += 1

            for wid in actual_matches:
                s = stats[wid]
                s["count"] += 1

                if year is None:
                    s["without_year"] += 1
                else:
                    s["with_year"] += 1
                    s["years"].append(year)

                if date_status == "YEAR_WITH_INVALID_DATE_COMPONENTS":
                    s["incomplete"] += 1

                if ed.get("languages"):
                    s["with_language"] += 1

                if ed.get("publishers"):
                    s["with_publisher"] += 1

    summary_path = partial / "work_edition_summary_v1.tsv"

    with summary_path.open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.writer(
            f, delimiter="\t", lineterminator="\n"
        )
        writer.writerow(SUMMARY_COLUMNS)

        for wid in sorted(targets):
            s = stats[wid]
            count = s["count"]

            assert (
                count == s["with_year"] + s["without_year"]
            )

            years = s["years"]

            writer.writerow([
                wid,
                count,
                s["with_year"],
                s["without_year"],
                s["incomplete"],
                min(years) if years else None,
                max(years) if years else None,
                s["with_language"],
                count - s["with_language"],
                s["with_publisher"],
                count - s["with_publisher"],
            ])

    outputs = [
        details_path,
        links_path,
        summary_path,
    ]

    manifest = {
        "status": "LOCAL_VALIDATION_NOT_PUBLISHED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_snapshot": args.snapshot,
        "input_jsonl": str(source),
        "input_sha256": sha256(source),
        "upstream_manifest": (
            str(args.upstream_manifest.resolve())
            if args.upstream_manifest else None
        ),
        "upstream_manifest_sha256": (
            sha256(args.upstream_manifest.resolve())
            if args.upstream_manifest else None
        ),
        "upstream_source_file": (
            upstream.get("source_file") if upstream else None
        ),
        "upstream_source_sha256": (
            upstream.get("source_sha256") if upstream else None
        ),
        "builder_sha256": sha256(Path(__file__).resolve()),
        "date_parser_sha256": sha256(
            Path(__file__).with_name(
                "parse_ol_edition_date_v1.py"
            ).resolve()
        ),
        "target_work_count": len(targets),
        "unique_edition_count": len(seen_editions),
        "edition_work_link_count": link_count,
        "duplicate_work_link_entries": duplicate_link_entries,
        "work_summary_rows": len(targets),
        "outputs": {
            p.name: {
                "bytes": p.stat().st_size,
                "sha256": sha256(p),
            }
            for p in outputs
        },
        "interpretation": (
            "Open Library registered Edition records in the "
            "selected snapshot; not historical publication totals."
        ),
    }

    with (partial / "manifest_v1.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Publish the complete local output directory atomically.
    partial.rename(dest)

    print(json.dumps(
        manifest, indent=2, ensure_ascii=False
    ))


if __name__ == "__main__":
    main()
