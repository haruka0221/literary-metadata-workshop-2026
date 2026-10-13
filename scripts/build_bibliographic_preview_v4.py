#!/usr/bin/env python3
"""Append fixed-snapshot OL Edition evidence to workshop preview v3."""

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.home() / "workshop-20261016"

PREVIEW = ROOT / (
    "previews/ol_wikidata_openalex_bibliographic_preview_v3.csv"
)
PROJECTION = ROOT / (
    "data_sources/ol_historical_edition_projection_20260228_v1/"
    "historical_targets_edition_summary_v1.tsv"
)
QUALITY = ROOT / (
    "data_sources/ol_editions_34792targets_slices_20260228_v1/"
    "work_edition_quality_v1.tsv"
)

DEST = ROOT / "previews/ol_wikidata_openalex_bibliographic_preview_v4"
PARTIAL = DEST.parent / f".{DEST.name}.incomplete"

SNAPSHOT = "2026-02-28"

ADDED = [
    "ol_edition_fixed_snapshot",
    "ol_20260228_historical_edition_count",
    "ol_20260228_current_edition_count",
    "ol_20260228_historical_year_known",
    "ol_20260228_current_year_known",
    "ol_20260228_historical_earliest_year",
    "ol_20260228_current_earliest_year",
    "ol_20260228_historical_latest_year",
    "ol_20260228_current_latest_year",
    "ol_20260228_historical_year_unknown",
    "ol_20260228_current_year_unknown",
    "ol_20260228_historical_language_missing",
    "ol_20260228_current_language_missing",
    "ol_20260228_historical_year_outliers",
    "ol_20260228_current_year_outliers",
]


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path, delimiter, key):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        fields = reader.fieldnames
        rows = list(reader)

    if not fields or key not in fields:
        raise ValueError(f"Missing key column: {path}")

    ids = [r[key] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError(f"Duplicate IDs: {path}")

    return fields, rows, {r[key]: r for r in rows}


def main():
    if DEST.exists() or PARTIAL.exists():
        raise FileExistsError("Output directory already exists")

    fields, previews, _ = load(
        PREVIEW, ",", "historical_ol_work_id"
    )
    _, projected, proj_by_id = load(
        PROJECTION, "\t", "historical_ol_work_id"
    )
    _, quality, quality_by_id = load(
        QUALITY, "\t", "source_ol_work_id"
    )

    if len(previews) != 34789 or len(projected) != 34789:
        raise ValueError("Unexpected historical population size")

    if len(quality) != 34792:
        raise ValueError("Unexpected quality-table Work count")

    if set(fields) & set(ADDED):
        raise ValueError("New columns already exist in preview")

    if {r["historical_ol_work_id"] for r in previews} != set(proj_by_id):
        raise ValueError("Preview and projection populations differ")

    corrected = 0
    historical_total = 0
    current_total = 0
    legacy_checked = 0
    output_rows = []

    for old in previews:
        historical_id = old["historical_ol_work_id"]
        current_id = old["current_ol_work_id"]
        p = proj_by_id[historical_id]

        for field in (
            "current_ol_work_id",
            "historical_entity_id",
            "current_entity_id",
            "target_resolution",
        ):
            if old[field] != p[field]:
                raise ValueError(
                    f"Mapping mismatch: {historical_id}: {field}"
                )

        changed = historical_id != current_id
        if changed != (p["is_corrected_target"] == "1"):
            raise ValueError("Correction flag mismatch")

        corrected += int(changed)

        hcount = int(p["historical_edition_count"])
        ccount = int(p["current_edition_count"])

        legacy = old["ol_historical_work_edition_count"]
        if legacy:
            if int(legacy) != hcount:
                raise ValueError(
                    f"Legacy Edition count mismatch: {historical_id}"
                )
            legacy_checked += 1

        for prefix, wid, count in (
            ("historical", historical_id, hcount),
            ("current", current_id, ccount),
        ):
            if wid not in quality_by_id:
                raise ValueError(f"Missing quality data: {wid}")
            if int(quality_by_id[wid]["edition_count"]) != count:
                raise ValueError(f"Quality count mismatch: {wid}")

        hq = quality_by_id[historical_id]
        cq = quality_by_id[current_id]

        def outliers(q):
            return str(
                int(q["year_before_review_min"])
                + int(q["year_after_review_max"])
            )

        extra = {
            "ol_edition_fixed_snapshot": SNAPSHOT,
            "ol_20260228_historical_edition_count": str(hcount),
            "ol_20260228_current_edition_count": str(ccount),
            "ol_20260228_historical_year_known":
                p["historical_editions_with_publish_year"],
            "ol_20260228_current_year_known":
                p["current_editions_with_publish_year"],
            "ol_20260228_historical_earliest_year":
                p["historical_earliest_observed_edition_year"],
            "ol_20260228_current_earliest_year":
                p["current_earliest_observed_edition_year"],
            "ol_20260228_historical_latest_year":
                p["historical_latest_observed_edition_year"],
            "ol_20260228_current_latest_year":
                p["current_latest_observed_edition_year"],
            "ol_20260228_historical_year_unknown":
                hq["year_unknown"],
            "ol_20260228_current_year_unknown":
                cq["year_unknown"],
            "ol_20260228_historical_language_missing":
                hq["language_missing"],
            "ol_20260228_current_language_missing":
                cq["language_missing"],
            "ol_20260228_historical_year_outliers":
                outliers(hq),
            "ol_20260228_current_year_outliers":
                outliers(cq),
        }

        output_rows.append({**old, **extra})
        historical_total += hcount
        current_total += ccount

    assert corrected == 3
    assert historical_total == 420036
    assert current_total == 421749
    assert len(output_rows) == 34789

    PARTIAL.mkdir(parents=True)

    output = PARTIAL / "ol_wikidata_openalex_bibliographic_preview_v4.csv"

    with output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields + ADDED,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output_rows)

    manifest = {
        "status": "LOCAL_VALIDATION_NOT_PUBLISHED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "historical_rows": len(output_rows),
        "original_columns": len(fields),
        "added_columns": len(ADDED),
        "corrected_rows": corrected,
        "historical_edition_count_sum": historical_total,
        "current_edition_count_sum": current_total,
        "legacy_counts_checked": legacy_checked,
        "inputs": {
            str(path): sha256(path)
            for path in (PREVIEW, PROJECTION, QUALITY)
        },
        "builder_sha256": sha256(Path(__file__).resolve()),
        "output_sha256": sha256(output),
        "output_bytes": output.stat().st_size,
        "interpretation": (
            "Original preview columns retained unchanged. "
            "Fixed-snapshot Edition observations appended separately. "
            "Wikidata holds and provisional OpenAlex counts unchanged."
        ),
    }

    (PARTIAL / "manifest_v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    PARTIAL.rename(DEST)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
