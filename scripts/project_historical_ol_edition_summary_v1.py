#!/usr/bin/env python3
"""Project Work-level Edition summaries onto historical OL source rows."""

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


MAP_COLUMNS = [
    "historical_entity_id",
    "historical_ol_work_id",
    "current_entity_id",
    "current_ol_work_id",
    "target_resolution",
]

SUMMARY_FIELDS = [
    "edition_count",
    "editions_with_publish_year",
    "editions_without_publish_year",
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


def read_tsv(path):
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        columns = reader.fieldnames or []
        rows = list(reader)
    return columns, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mapping", required=True, type=Path)
    ap.add_argument("--summary", required=True, type=Path)
    ap.add_argument("--dest", required=True, type=Path)
    args = ap.parse_args()

    mapping_path = args.mapping.resolve()
    summary_path = args.summary.resolve()
    dest = args.dest.resolve()
    partial = dest.parent / f".{dest.name}.incomplete"

    if dest.exists() or partial.exists():
        raise FileExistsError("Destination or partial output already exists")

    map_columns, mapping = read_tsv(mapping_path)
    summary_columns, summary_rows = read_tsv(summary_path)

    assert set(MAP_COLUMNS) <= set(map_columns)
    assert {"source_ol_work_id", *SUMMARY_FIELDS} <= set(summary_columns)

    summary = {}
    for row in summary_rows:
        wid = row["source_ol_work_id"]
        if wid in summary:
            raise ValueError(f"Duplicate summary Work ID: {wid}")
        summary[wid] = row

    historical_ids = [r["historical_ol_work_id"] for r in mapping]
    current_ids = [r["current_ol_work_id"] for r in mapping]

    if len(historical_ids) != len(set(historical_ids)):
        raise ValueError("Duplicate historical Work ID")

    if len(current_ids) != len(set(current_ids)):
        raise ValueError("Duplicate current Work ID")

    expected_ids = set(historical_ids) | set(current_ids)
    if expected_ids != set(summary):
        raise ValueError(
            f"Target mismatch: missing={len(expected_ids-set(summary))}, "
            f"unexpected={len(set(summary)-expected_ids)}"
        )

    columns = (
        MAP_COLUMNS
        + ["is_corrected_target"]
        + [f"historical_{x}" for x in SUMMARY_FIELDS]
        + [f"current_{x}" for x in SUMMARY_FIELDS]
    )

    output_rows = []
    corrected = 0

    for row in mapping:
        historical_id = row["historical_ol_work_id"]
        current_id = row["current_ol_work_id"]
        changed = historical_id != current_id
        corrected += int(changed)

        output = {k: row[k] for k in MAP_COLUMNS}
        output["is_corrected_target"] = str(int(changed))

        for prefix, wid in [
            ("historical", historical_id),
            ("current", current_id),
        ]:
            source = summary[wid]
            for field in SUMMARY_FIELDS:
                output[f"{prefix}_{field}"] = source[field]

        output_rows.append(output)

    dest.parent.mkdir(parents=True, exist_ok=True)
    partial.mkdir()

    output_path = partial / "historical_targets_edition_summary_v1.tsv"

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output_rows)

    manifest = {
        "status": "LOCAL_VALIDATION_NOT_PUBLISHED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "mapping_source": str(mapping_path),
        "mapping_sha256": sha256(mapping_path),
        "work_summary_source": str(summary_path),
        "work_summary_sha256": sha256(summary_path),
        "builder_sha256": sha256(Path(__file__).resolve()),
        "historical_rows": len(output_rows),
        "corrected_target_rows": corrected,
        "unique_input_work_ids": len(summary),
        "output_file": output_path.name,
        "output_sha256": sha256(output_path),
        "output_bytes": output_path.stat().st_size,
        "interpretation": (
            "Historical and current OL Work Edition summaries "
            "remain separate; counts are never combined."
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
