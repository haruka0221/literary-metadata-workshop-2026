#!/usr/bin/env python3
"""Extract four selected OL Work Edition records from one frozen OL Editions dump.

Read-only against source. A smoke test (--max-records) writes nothing.
A complete scan atomically publishes separate, new JSONL and manifest files.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

WORKS = {
    "OL47721W": "News from Nowhere (selected OL Work)",
    "OL2981506W": "Looking Backward (selected OL Work)",
    "OL22364W": "Erewhon (selected OL Work)",
    "OL879241W": "A Crystal Age (selected OL Work)",
}
DEFAULT_SOURCE = Path(
    "/media/hdd1/user/tsutsui/openlibrary/ol_dump_editions_2026-02-28.txt.gz"
)
DEFAULT_DEST = Path.home() / "workshop-20261016/data_sources/ol_editions_fourworks_dump_20260228_v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--max-records", type=int, default=0,
                        help="Read only first N records, print inspection summary and write NOTHING. Default 0: full scan.")
    args = parser.parse_args()
    if args.max_records < 0:
        parser.error("--max-records must be >= 0")
    source = args.source.expanduser().resolve()
    dest = args.dest.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    output = dest / "fourworks_edition_records_v1.jsonl"
    manifest_file = dest / "manifest_v1.json"
    temporary = dest / ".fourworks_edition_records_v1.jsonl.tmp"
    if not args.max_records:
        if output.exists() or manifest_file.exists() or temporary.exists():
            raise FileExistsError("Output/manifest/temp already exists; refusing to overwrite: " + str(dest))
        dest.mkdir(parents=True, exist_ok=True)
    scanned = 0
    matched_count = Counter()
    matched_editions: set[str] = set()
    multiwork_records = 0
    record_parse_errors = 0
    candidate_lines = 0
    start = datetime.now(timezone.utc).isoformat()
    # This cheap text prefilter is only an optimization. All candidate hits are verified
    # against the edition's structured `works` list before inclusion.
    needles = tuple(("/works/" + wid).encode("ascii") for wid in WORKS)
    out = None
    try:
        if not args.max_records:
            out = temporary.open("w", encoding="utf-8", newline="\n")
        with gzip.open(source, "rb") as stream:
            for line in stream:
                scanned += 1
                if args.max_records and scanned > args.max_records:
                    scanned -= 1
                    break
                if scanned % 1_000_000 == 0:
                    print(f"Scanned {scanned:,} records", file=sys.stderr, flush=True)
                if not any(needle in line for needle in needles):
                    continue
                candidate_lines += 1
                fields = line.rstrip(b"\r\n").split(b"\t", 4)
                if len(fields) != 5 or fields[0] != b"/type/edition":
                    record_parse_errors += 1
                    raise ValueError(f"Malformed matched TSV record at line {scanned}")
                try:
                    obj = json.loads(fields[4])
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    record_parse_errors += 1
                    raise ValueError(f"Invalid matched JSON at line {scanned}") from exc
                edition_key = obj.get("key")
                if not isinstance(edition_key, str) or edition_key != fields[1].decode("utf-8"):
                    raise ValueError(f"Missing or mismatched Edition key at line {scanned}")
                links = obj.get("works")
                if links is None:
                    links = []
                if not isinstance(links, list):
                    raise ValueError(f"Invalid works list for {edition_key}")
                all_work_keys = []
                for item in links:
                    if isinstance(item, dict) and isinstance(item.get("key"), str):
                        all_work_keys.append(item["key"])
                matches = [wid for wid in WORKS if "/works/" + wid in all_work_keys]
                if not matches:
                    continue
                if edition_key in matched_editions:
                    raise ValueError(f"Duplicate Edition key in matched set: {edition_key}")
                matched_editions.add(edition_key)
                if len(all_work_keys) > 1:
                    multiwork_records += 1
                for wid in matches:
                    matched_count[wid] += 1
                if out is not None:
                    out.write(json.dumps({
                        "edition_key": edition_key,
                        "matched_selected_work_ids": matches,
                        "all_work_keys": all_work_keys,
                        "edition_record": obj,
                    }, ensure_ascii=False, separators=(",", ":")) + "\n")
                # Other lines have no need for JSON parsing.
        if out is not None:
            out.flush()
            out.close()
            out = None
        summary = {
            "status": "SMOKE_TEST_NO_FILES_WRITTEN" if args.max_records else "EXTRACTION_COMPLETE_NOT_PUBLISHED",
            "source_file": str(source),
            "source_size_bytes": source.stat().st_size,
            "source_mtime_utc": datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
            "source_sha256": None,
            "source_sha256_note": "Full source-content hash not calculated; record upstream snapshot provenance separately.",
            "scan_started_utc": start,
            "scan_finished_utc": datetime.now(timezone.utc).isoformat(),
            "max_records": args.max_records,
            "scanned_rows": scanned,
            "candidate_text_rows": candidate_lines,
            "candidate_parse_errors": record_parse_errors,
            "matched_unique_editions": len(matched_editions),
            "editions_with_multiple_source_work_links": multiwork_records,
            "per_selected_work": {
                wid: {"label": label, "matched_edition_count": matched_count[wid]}
                for wid, label in WORKS.items()
            },
            "method": "stream gzip TSV; exact membership in edition_record.works; 4 selected OL Work IDs only",
            "interpretation": "Edition records in this dump, not all historical published editions",
        }
        if out is None and not args.max_records:
            summary["output_jsonl"] = str(output)
            summary["output_sha256"] = sha256(temporary)
            with (dest / ".manifest_v1.json.tmp").open("w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
                f.write("\n")
            temporary.rename(output)
            (dest / ".manifest_v1.json.tmp").rename(manifest_file)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        if out is not None:
            out.close()


if __name__ == "__main__":
    main()
