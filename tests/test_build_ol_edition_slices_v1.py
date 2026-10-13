"""Regression tests for OL Edition decade/language slices."""

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_ol_edition_slices_v1.py"

W1 = "OL900001W"
W2 = "OL900002W"
OUTSIDE = "OL900003W"


def write_tsv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=columns,
            delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def detail(eid, year, status, languages):
    return {
        "edition_key": f"/books/{eid}",
        "publish_year": year,
        "publish_year_parse_status": status,
        "languages_json": json.dumps(languages),
    }


def lang(*codes):
    return [{"key": f"/languages/{c}"} for c in codes]


def prepare(root, wrong_count=False):
    details = root / "details.tsv"
    links = root / "links.tsv"
    summary = root / "summary.tsv"

    write_tsv(details, [
        "edition_key", "publish_year",
        "publish_year_parse_status", "languages_json"
    ], [
        detail("OL900001M", "1890", "EXACT_YEAR",
               lang("eng", "eng", "spa")),
        detail("OL900002M", "", "MISSING", None),
        detail("OL900003M", "1800", "EXACT_YEAR",
               lang("und")),
        detail("OL900004M", "2098", "EXACT_YEAR",
               lang("fre")),
        detail("OL900005M", "1900",
               "YEAR_WITH_INVALID_DATE_COMPONENTS",
               lang("eng")),
    ])

    def link(eid, wid, target):
        return {
            "edition_key": f"/books/{eid}",
            "source_ol_work_id": wid,
            "is_extraction_target": str(int(target)),
        }

    write_tsv(links, [
        "edition_key", "source_ol_work_id",
        "is_extraction_target"
    ], [
        link("OL900001M", W1, True),
        link("OL900001M", W2, True),
        link("OL900001M", OUTSIDE, False),
        link("OL900002M", W1, True),
        link("OL900003M", W2, True),
        link("OL900004M", W2, True),
        link("OL900005M", W1, True),
    ])

    write_tsv(summary, [
        "source_ol_work_id", "edition_count"
    ], [
        {"source_ol_work_id": W1,
         "edition_count": "99" if wrong_count else "3"},
        {"source_ol_work_id": W2, "edition_count": "3"},
    ])

    return details, links, summary


def run_builder(paths, dest):
    details, links, summary = paths
    return subprocess.run([
        sys.executable, "-B", str(SCRIPT),
        "--details", str(details),
        "--links", str(links),
        "--summary", str(summary),
        "--dest", str(dest),
        "--review-min-year", "1880",
        "--review-max-year", "2026",
    ], capture_output=True, text=True)


class TestEditionSlices(unittest.TestCase):

    def test_multilingual_decades_and_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = prepare(root)
            dest = root / "output"

            result = run_builder(paths, dest)
            self.assertEqual(result.returncode, 0, result.stderr)

            decades = read_tsv(
                dest / "work_edition_by_decade_v1.tsv"
            )
            languages = read_tsv(
                dest / "work_edition_by_language_v1.tsv"
            )
            quality = read_tsv(
                dest / "work_edition_quality_v1.tsv"
            )

            decade_counts = {
                (r["source_ol_work_id"],
                 r["decade_start_year"],
                 r["year_review_category"]):
                int(r["edition_count"])
                for r in decades
            }

            self.assertEqual(decade_counts, {
                (W1, "1890", "OBSERVED"): 1,
                (W1, "1900", "OBSERVED"): 1,
                (W1, "UNKNOWN", "UNKNOWN"): 1,
                (W2, "1800", "BEFORE_REVIEW_MIN"): 1,
                (W2, "1890", "OBSERVED"): 1,
                (W2, "2090", "AFTER_REVIEW_MAX"): 1,
            })

            language_counts = {
                (r["source_ol_work_id"],
                 r["language_code"]):
                int(r["edition_count"])
                for r in languages
            }

            self.assertEqual(language_counts, {
                (W1, "eng"): 2,
                (W1, "spa"): 1,
                (W1, "__MISSING__"): 1,
                (W2, "eng"): 1,
                (W2, "spa"): 1,
                (W2, "und"): 1,
                (W2, "fre"): 1,
            })

            q = {
                r["source_ol_work_id"]: r
                for r in quality
            }

            self.assertEqual(len(q), 2)

            self.assertEqual(q[W1]["edition_count"], "3")
            self.assertEqual(q[W1]["year_unknown"], "1")
            self.assertEqual(q[W1]["language_missing"], "1")
            self.assertEqual(
                q[W1]["duplicate_language_tags"], "1"
            )
            self.assertEqual(
                q[W1]["multiple_distinct_languages"], "1"
            )
            self.assertEqual(q[W1]["incomplete_date"], "1")

            self.assertEqual(q[W2]["edition_count"], "3")
            self.assertEqual(
                q[W2]["year_before_review_min"], "1"
            )
            self.assertEqual(
                q[W2]["year_after_review_max"], "1"
            )
            self.assertEqual(
                q[W2]["explicit_und_language"], "1"
            )

            manifest = json.loads(
                (dest / "manifest_v1.json").read_text()
            )

            self.assertEqual(manifest["unique_editions"], 5)
            self.assertEqual(manifest["all_work_links"], 7)
            self.assertEqual(manifest["target_work_links"], 6)
            self.assertEqual(manifest["target_work_count"], 2)

            for name, info in manifest["outputs"].items():
                p = dest / name
                actual = hashlib.sha256(p.read_bytes()).hexdigest()
                self.assertEqual(info["sha256"], actual)

    def test_wrong_work_count_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = prepare(root, wrong_count=True)
            dest = root / "output"

            result = run_builder(paths, dest)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Work count mismatch", result.stderr)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
