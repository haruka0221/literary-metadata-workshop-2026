"""Tests for historical/current Open Library Edition projection."""

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/project_historical_ol_edition_summary_v1.py"

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


def write_tsv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=columns, delimiter="\t"
        )
        writer.writeheader()
        writer.writerows(rows)


def summary_row(wid, count):
    return {
        "source_ol_work_id": wid,
        "edition_count": str(count),
        "editions_with_publish_year": str(count),
        "editions_without_publish_year": "0",
        "editions_with_incomplete_date": "0",
        "earliest_observed_edition_year": "1890",
        "latest_observed_edition_year": "1920",
        "editions_with_language_metadata": str(count),
        "editions_without_language_metadata": "0",
        "editions_with_publisher_metadata": str(count),
        "editions_without_publisher_metadata": "0",
    }


def prepare(root, omit_current=False):
    mapping = root / "mapping.tsv"
    summary = root / "summary.tsv"

    write_tsv(mapping, MAP_COLUMNS, [
        {
            "historical_entity_id": "historical-A",
            "historical_ol_work_id": "OL900001W",
            "current_entity_id": "current-A",
            "current_ol_work_id": "OL900001W",
            "target_resolution": "unchanged",
        },
        {
            "historical_entity_id": "historical-B",
            "historical_ol_work_id": "OL900002W",
            "current_entity_id": "current-B",
            "current_ol_work_id": "OL900003W",
            "target_resolution": "corrected",
        },
    ])

    records = [
        summary_row("OL900001W", 2),
        summary_row("OL900002W", 1),
    ]

    if not omit_current:
        records.append(summary_row("OL900003W", 7))

    write_tsv(
        summary,
        ["source_ol_work_id"] + SUMMARY_FIELDS,
        records,
    )

    return mapping, summary


def run_builder(mapping, summary, dest):
    return subprocess.run(
        [
            sys.executable, "-B", str(SCRIPT),
            "--mapping", str(mapping),
            "--summary", str(summary),
            "--dest", str(dest),
        ],
        capture_output=True,
        text=True,
    )


class TestHistoricalProjection(unittest.TestCase):

    def test_preserves_historical_and_current_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping, summary = prepare(root)
            dest = root / "output"

            result = run_builder(mapping, summary, dest)
            self.assertEqual(result.returncode, 0, result.stderr)

            output = dest / "historical_targets_edition_summary_v1.tsv"

            with output.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f, delimiter="\t"))

            self.assertEqual(len(rows), 2)

            # Unchanged Work keeps the same count on both sides.
            self.assertEqual(rows[0]["historical_edition_count"], "2")
            self.assertEqual(rows[0]["current_edition_count"], "2")
            self.assertEqual(rows[0]["is_corrected_target"], "0")

            # Corrected Work retains two independent counts.
            self.assertEqual(rows[1]["historical_edition_count"], "1")
            self.assertEqual(rows[1]["current_edition_count"], "7")
            self.assertEqual(rows[1]["is_corrected_target"], "1")

            self.assertEqual(
                sum(int(r["historical_edition_count"]) for r in rows),
                3,
            )
            self.assertEqual(
                sum(int(r["current_edition_count"]) for r in rows),
                9,
            )

            manifest = json.loads(
                (dest / "manifest_v1.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["historical_rows"], 2)
            self.assertEqual(manifest["corrected_target_rows"], 1)
            self.assertEqual(manifest["unique_input_work_ids"], 3)
            self.assertEqual(
                manifest["output_sha256"],
                hashlib.sha256(output.read_bytes()).hexdigest(),
            )

    def test_missing_current_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping, summary = prepare(root, omit_current=True)
            dest = root / "output"

            result = run_builder(mapping, summary, dest)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Target mismatch", result.stderr)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
