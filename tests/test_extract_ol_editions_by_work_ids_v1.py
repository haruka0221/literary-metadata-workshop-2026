"""Regression tests for generic Open Library Edition extraction."""

import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/extract_ol_editions_by_work_ids_v1.py"

TARGETS = ["OL900001W", "OL900002W", "OL900004W"]


def make_edition(eid, works):
    return {
        "key": f"/books/{eid}",
        "title": "Synthetic Edition",
        "works": [
            {"key": f"/works/{wid}"} for wid in works
        ],
        "publish_date": "1890",
    }


def prepare_fixture(root):
    records = [
        make_edition("OL900001M", [
            "OL900001W",
            "OL900002W",
            "OL900002W",
            "OL900003W",
        ]),
        make_edition("OL900002M", ["OL900003W"]),
        make_edition("OL900003M", ["OL900001W"]),
        make_edition("OL900004M", []),
    ]

    source = root / "synthetic_dump.txt.gz"

    with gzip.open(source, "wt", encoding="utf-8") as f:
        for ed in records:
            fields = [
                "/type/edition",
                ed["key"],
                "1",
                "2026-02-28T00:00:00",
                json.dumps(ed, ensure_ascii=False),
            ]
            f.write("\t".join(fields) + "\n")

    targets = root / "targets.txt"
    targets.write_text(
        "".join(w + "\n" for w in TARGETS),
        encoding="utf-8",
    )

    return source, targets


def execute(source, targets, *arguments):
    command = [
        sys.executable, "-B", str(SCRIPT),
        "--source", str(source),
        "--targets-file", str(targets),
        *arguments,
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


class TestEditionExtractor(unittest.TestCase):

    def test_smoke_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, targets = prepare_fixture(root)

            result = execute(
                source, targets,
                "--max-records", "3",
            )

            self.assertEqual(
                result["status"], "SMOKE_TEST_NO_FILES_WRITTEN"
            )
            self.assertEqual(result["scanned_rows"], 3)
            self.assertEqual(result["matched_unique_editions"], 2)
            self.assertFalse((root / "output").exists())

    def test_full_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, targets = prepare_fixture(root)
            dest = root / "output"

            result = execute(
                source, targets,
                "--dest", str(dest),
                "--full-scan",
            )

            self.assertEqual(result["scanned_rows"], 4)
            self.assertEqual(result["target_work_count"], 3)
            self.assertEqual(result["matched_unique_editions"], 2)
            self.assertEqual(result["matched_target_works"], 2)
            self.assertEqual(
                result["editions_with_multiple_source_work_links"], 1
            )
            self.assertEqual(result["duplicate_work_link_entries"], 1)

            output = dest / "edition_records_v1.jsonl"
            records = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual(len(records), 2)
            self.assertEqual(
                records[0]["matched_selected_work_ids"],
                ["OL900001W", "OL900002W"],
            )
            self.assertEqual(
                records[0]["all_work_keys"],
                [
                    "/works/OL900001W",
                    "/works/OL900002W",
                    "/works/OL900002W",
                    "/works/OL900003W",
                ],
            )

            manifest = json.loads(
                (dest / "manifest_v1.json").read_text()
            )
            actual_hash = hashlib.sha256(output.read_bytes()).hexdigest()

            self.assertEqual(manifest["output_sha256"], actual_hash)
            self.assertEqual(
                manifest["status"],
                "EXTRACTION_COMPLETE_NOT_PUBLISHED",
            )


    def test_duplicate_same_work_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "duplicate_dump.txt.gz"
            targets = root / "targets.txt"
            dest = root / "output"

            ed = make_edition(
                "OL900005M",
                ["OL900001W", "OL900001W"],
            )

            with gzip.open(source, "wt", encoding="utf-8") as f:
                f.write("\t".join([
                    "/type/edition",
                    ed["key"],
                    "1",
                    "2026-02-28T00:00:00",
                    json.dumps(ed),
                ]) + "\n")

            targets.write_text(
                "OL900001W\n", encoding="utf-8"
            )

            result = execute(
                source, targets,
                "--dest", str(dest),
                "--full-scan",
            )

            self.assertEqual(
                result["matched_unique_editions"], 1
            )
            self.assertEqual(
                result["duplicate_work_link_entries"], 1
            )
            self.assertEqual(
                result["editions_with_multiple_source_work_links"], 0
            )

            records = [
                json.loads(line)
                for line in (
                    dest / "edition_records_v1.jsonl"
                ).read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual(len(records), 1)
            self.assertEqual(
                records[0]["matched_selected_work_ids"],
                ["OL900001W"],
            )


if __name__ == "__main__":
    unittest.main()
