#!/usr/bin/env python3
"""Extract OL Edition records for an arbitrary set of Work IDs.

Smoke tests write nothing. Full scans require --full-scan.
Source dumps and existing outputs are never overwritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_targets(path):
    with path.open(encoding="utf-8-sig") as f:
        values = [
            line.strip()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ]

    if not values:
        raise ValueError("Empty target list")

    if len(values) != len(set(values)):
        raise ValueError("Duplicate target IDs")

    if any(not re.fullmatch(r"OL[0-9]+W", x) for x in values):
        raise ValueError("Invalid OL Work ID")

    return set(values)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--targets-file", required=True, type=Path)
    ap.add_argument("--target-manifest", type=Path)
    ap.add_argument("--dest", type=Path)

    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--max-records", type=int)
    mode.add_argument("--full-scan", action="store_true")

    args = ap.parse_args()

    if args.max_records is not None and args.max_records <= 0:
        ap.error("--max-records must be positive")

    if args.full_scan and args.dest is None:
        ap.error("--dest is required for --full-scan")

    source = args.source.expanduser().resolve()
    target_file = args.targets_file.expanduser().resolve()

    if not source.is_file():
        raise FileNotFoundError(source)

    targets = read_targets(target_file)

    if args.target_manifest:
        mp = args.target_manifest.expanduser().resolve()
        manifest = json.loads(mp.read_text(encoding="utf-8"))

        if sha256(target_file) != manifest["target_file_sha256"]:
            raise ValueError("Target file SHA256 mismatch")

        if len(targets) != manifest["extraction_target_unique_ids"]:
            raise ValueError("Target count mismatch")

    dest = None
    partial = None
    out = None

    if args.full_scan:
        dest = args.dest.expanduser().resolve()
        partial = dest.parent / f".{dest.name}.incomplete"

        if dest.exists() or partial.exists():
            raise FileExistsError(
                "Output or incomplete directory already exists"
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        partial.mkdir()
        out = (partial / "edition_records_v1.jsonl").open(
            "w", encoding="utf-8", newline="\n"
        )

    source_stat = source.stat()
    started = utc_now()

    scanned = 0
    matched = 0
    multiwork = 0
    duplicate_link_entries = 0
    per_work = Counter()
    seen_editions = set()

    try:
        with gzip.open(source, "rb") as stream:
            for line in stream:
                if (
                    args.max_records is not None
                    and scanned >= args.max_records
                ):
                    break

                scanned += 1

                if scanned % 1_000_000 == 0:
                    print(
                        f"Scanned {scanned:,} rows",
                        file=sys.stderr,
                        flush=True,
                    )

                fields = line.rstrip(b"\r\n").split(b"\t", 4)

                if len(fields) != 5:
                    raise ValueError(
                        f"Malformed TSV at line {scanned}"
                    )

                if fields[0] != b"/type/edition":
                    raise ValueError(
                        f"Unexpected record type at line {scanned}"
                    )

                try:
                    obj = json.loads(fields[4])
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        f"Invalid JSON at line {scanned}"
                    ) from exc

                edition_key = obj.get("key")
                tsv_key = fields[1].decode("utf-8")

                if not isinstance(edition_key, str):
                    raise ValueError(
                        f"Missing Edition key at line {scanned}"
                    )

                if edition_key != tsv_key:
                    raise ValueError(
                        f"Edition key mismatch at line {scanned}"
                    )

                links = obj.get("works")
                if links is None:
                    links = []

                if not isinstance(links, list):
                    raise ValueError(
                        f"Invalid works field: {edition_key}"
                    )

                all_keys = [
                    item["key"]
                    for item in links
                    if isinstance(item, dict)
                    and isinstance(item.get("key"), str)
                ]

                matched_ids = sorted({
                    key.removeprefix("/works/")
                    for key in all_keys
                    if key.startswith("/works/")
                    and key.removeprefix("/works/") in targets
                })

                if not matched_ids:
                    continue

                if edition_key in seen_editions:
                    raise ValueError(
                        f"Duplicate Edition: {edition_key}"
                    )

                seen_editions.add(edition_key)
                matched += 1

                if len(set(all_keys)) > 1:
                    multiwork += 1

                duplicate_link_entries += (
                    len(all_keys) - len(set(all_keys))
                )

                for wid in matched_ids:
                    per_work[wid] += 1

                if out is not None:
                    out.write(json.dumps({
                        "edition_key": edition_key,
                        "matched_selected_work_ids": matched_ids,
                        "all_work_keys": all_keys,
                        "edition_record": obj,
                    }, ensure_ascii=False, separators=(",", ":")) + "\n")

        if out is not None:
            out.close()
            out = None

        if args.full_scan:
            latest_stat = source.stat()
            if (
                latest_stat.st_size != source_stat.st_size
                or latest_stat.st_mtime_ns != source_stat.st_mtime_ns
            ):
                raise RuntimeError("Source changed during scan")

        result = {
            "status": (
                "EXTRACTION_COMPLETE_NOT_PUBLISHED"
                if args.full_scan
                else "SMOKE_TEST_NO_FILES_WRITTEN"
            ),
            "source_file": str(source),
            "source_size_bytes": source_stat.st_size,
            "source_mtime_utc": datetime.fromtimestamp(
                source_stat.st_mtime, timezone.utc
            ).isoformat(),
            "source_sha256": None,
            "source_sha256_note": (
                "Compressed source byte hash not yet calculated"
            ),
            "targets_file": str(target_file),
            "targets_sha256": sha256(target_file),
            "target_work_count": len(targets),
            "scan_mode": "STRICT_PARSE_ALL_EDITION_JSON",
            "started_utc": started,
            "finished_utc": utc_now(),
            "scanned_rows": scanned,
            "matched_unique_editions": matched,
            "matched_target_works": len(per_work),
            "editions_with_multiple_source_work_links": multiwork,
            "duplicate_work_link_entries": duplicate_link_entries,
            "builder_sha256": sha256(Path(__file__).resolve()),
        }

        if args.full_scan:
            output = partial / "edition_records_v1.jsonl"

            result["output_jsonl"] = str(
                dest / "edition_records_v1.jsonl"
            )
            result["output_bytes"] = output.stat().st_size
            result["output_sha256"] = sha256(output)

            (partial / "manifest_v1.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            partial.rename(dest)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    finally:
        if out is not None:
            out.close()


if __name__ == "__main__":
    main()
