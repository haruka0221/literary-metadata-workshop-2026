"""Regression tests for OL Edition publication-date parser."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from parse_ol_edition_date_v1 import parse_publish_date


class TestPublishDateParser(unittest.TestCase):

    def test_known_formats(self):
        cases = [
            ("1890", 1890, "EXACT_YEAR"),
            ("July 2003", 2003, "ENGLISH_MONTH_YEAR"),
            ("Sept 1997", 1997, "ENGLISH_MONTH_YEAR"),
            ("May 18, 2011", 2011, "ENGLISH_FULL_DATE"),
            ("Feb 28, 2020", 2020, "ENGLISH_FULL_DATE"),
            ("1928-01-01", 1928, "ISO_FULL_DATE"),
            ("2020-02-29", 2020, "ISO_FULL_DATE"),
            ("1924/00/00", 1924,
             "YEAR_WITH_INVALID_DATE_COMPONENTS"),
            ("189-?", None, "AMBIGUOUS"),
            (None, None, "MISSING"),
            ("", None, "MISSING"),
            ("   ", None, "MISSING"),
            ("2021-02-30", None, "UNPARSEABLE"),
            ("2019-02-29", None, "UNPARSEABLE"),
            ("0000", None, "UNPARSEABLE"),
            ("unknown", None, "UNPARSEABLE"),
        ]

        for raw, expected_year, expected_status in cases:
            with self.subTest(raw=raw):
                self.assertEqual(
                    parse_publish_date(raw),
                    (expected_year, expected_status),
                )


if __name__ == "__main__":
    unittest.main()
