"""Regression tests for Open Library Edition table builder v1."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/build_ol_edition_tables_v1.py"

TARGETS = [
    "OL900001W",
    "OL900002W",
    "OL900004W",
]


def make_record(eid, works, publish_date):
    keys = [f"/works/{w}" for w in works]

    edition = {
        "key": f"/books/{eid}",
        "title": "Synthetic test record",
        "works": [{"key": k} for k in keys],
        "publish_date": publish_date,
        "publishers": ["Publisher A", "Publisher B"],
        "languages": [
            {"key": "/languages/eng"},
            {"key": "/languages/fre"},
        ],
    }

    return {
        "edition_key": edition["key"],
        "matched_selected_work_ids": [
            w for w in TARGETS if w in works
        ],
        "all_work_keys": keys,
        "edition_record": edition,
    }


def read_tsv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


class TestEditionTableBuilder(unittest.TestCase):

    def test_multiwork_and_deduplication(self):
        records = [
            make_record(
                "OL900001M",
                [
                    "OL900001W",
                    "OL900002W",
                    "OL900002W",
                    "OL900003W",
                ],
                "1890",
            ),
            make_record(
                "OL900002M",
                ["OL900001W"],
                "189-?",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.jsonl"
            dest = root / "output"

            source.write_text(
                "".join(
                    json.dumps(r, ensure_ascii=False) + "\n"
                    for r in records
                ),
                encoding="utf-8",
            )

            cmd = [
                sys.executable,
                "-B",
                str(BUILDER),
                "--input", str(source),
                "--dest", str(dest),
                "--snapshot", "SYNTHETIC_TEST",
            ]

            for target in TARGETS:
                cmd.extend(["--target", target])

            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )

            details = read_tsv(
                dest / "edition_details_v1.tsv"
            )
            links = read_tsv(
                dest / "edition_work_links_v1.tsv"
            )
            summary = read_tsv(
                dest / "work_edition_summary_v1.tsv"
            )

            manifest = json.loads(
                (dest / "manifest_v1.json").read_text()
            )

            self.assertEqual(len(details), 2)
            self.assertEqual(len(links), 4)
            self.assertEqual(len(summary), 3)

            counts = {
                r["source_ol_work_id"]:
                    int(r["edition_count"])
                for r in summary
            }

            self.assertEqual(counts, {
                "OL900001W": 2,
                "OL900002W": 1,
                "OL900004W": 0,
            })

            # Non-target Work relationship is preserved.
            self.assertTrue(any(
                r["source_ol_work_id"] == "OL900003W"
                and r["is_extraction_target"] == "0"
                for r in links
            ))

            # Duplicate Work link does not inflate counts.
            self.assertEqual(
                manifest["duplicate_work_link_entries"], 1
            )

            # Original ordinal is retained.
            self.assertTrue(any(
                r["source_ol_work_id"] == "OL900003W"
                and r["work_link_ordinal"] == "3"
                for r in links
            ))

            # Multiple metadata values are preserved.
            self.assertEqual(
                json.loads(details[0]["publishers_json"]),
                ["Publisher A", "Publisher B"],
            )
            self.assertEqual(
                len(json.loads(details[0]["languages_json"])),
                2,
            )

            # Missing/ambiguous year remains distinguishable.
            self.assertEqual(
                details[1]["publish_year_parse_status"],
                "AMBIGUOUS",
            )
            self.assertEqual(
                details[1]["publish_year"], "",
            )

            # Output provenance is recorded.
            self.assertEqual(
                manifest["unique_edition_count"], 2
            )
            self.assertEqual(
                manifest["edition_work_link_count"], 4
            )


if __name__ == "__main__":
    unittest.main()
