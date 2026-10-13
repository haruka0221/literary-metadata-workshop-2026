#!/usr/bin/env python3
"""Build review-only searchable workshop data without changing research files."""

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

WS = Path.home() / "workshop-20261016"
RESEARCH = Path.home() / "canon-pipeline-openalex-a2val"

SOURCE = WS / (
    "previews/ol_wikidata_openalex_bibliographic_preview_v4/"
    "ol_wikidata_openalex_bibliographic_preview_v4.csv"
)
MEMBERS = RESEARCH / "derived/identity/aggregation_review_members_v1.tsv"
CAL = RESEARCH / (
    "derived/openalex_production/retrieval_calibration_profile_v3/"
    "full_inventory_57959e90/openalex_a12_candidate_query_evidence_v3.parquet"
)

OUTDIR = WS / "previews/workshop_search_preview_v1"
OUT = OUTDIR / "workshop_search_preview_v1.csv"


def read_csv(path, delimiter=","):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        fields = reader.fieldnames
        rows = list(reader)
    if not fields:
        raise ValueError(f"Missing header: {path}")
    return fields, rows


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if OUTDIR.exists():
        raise FileExistsError(OUTDIR)

    columns, source = read_csv(SOURCE)
    required = {
        "historical_ol_work_id", "current_ol_work_id",
        "ol_source_title", "ol_author_names_display",
        "ol_source_first_publish_year",
        "ol_20260228_historical_edition_count",
        "ol_20260228_current_edition_count",
        "identity_status", "project_work_id",
        "wikidata_effective_decision", "wikidata_effective_qid",
        "openalex_measurement_status", "openalex_candidate_pairs",
    }
    if not required <= set(columns):
        raise ValueError(f"Missing columns: {required - set(columns)}")

    assert len(source) == 34789
    assert len({r["historical_ol_work_id"] for r in source}) == 34789

    # Current OL Work -> unresolved group.
    mcols, members = read_csv(MEMBERS, "\t")
    assert {
        "source", "source_namespace", "source_id",
        "unit_anchor_entity_id", "is_current_target"
    } <= set(mcols)

    anchors = {}
    for m in members:
        if (
            m["source"] == "openlibrary"
            and m["source_namespace"] == "work"
            and m["is_current_target"].lower() in {"true", "1"}
        ):
            wid = m["source_id"]
            anchor = m["unit_anchor_entity_id"]
            if not wid or not anchor:
                raise ValueError("Invalid review member")
            if wid in anchors and anchors[wid] != anchor:
                raise ValueError(f"Conflicting anchors: {wid}")
            anchors[wid] = anchor

    # Author-matched OpenAlex IDs, deduplicated within each unresolved group.
    evidence = pq.read_table(CAL, columns=[
        "unresolved_unit_anchor_entity_id",
        "openalex_work_id",
        "author_a1_hit",
        "author_a2_hit",
    ])

    oa_by_anchor = defaultdict(set)

    for r in evidence.to_pylist():
        anchor = r["unresolved_unit_anchor_entity_id"]
        oid = r["openalex_work_id"]
        if anchor and oid and (
            r["author_a1_hit"] is True
            or r["author_a2_hit"] is True
        ):
            oa_by_anchor[anchor].add(oid)

    # Freeze known calibration results as a QC check.
    expected = {
        "E000011227": 352,   # News from Nowhere
        "E000006181": 314,   # Looking Backward
        "E000014025": 302,   # Treasure Island
        "E000018716": 1436,  # The Great Gatsby
    }
    for anchor, n in expected.items():
        assert len(oa_by_anchor[anchor]) == n, (anchor, n)

    fields = [
        "ol_work_id",
        "current_ol_work_id",
        "ol_title",
        "ol_author_name",
        "ol_first_publish_year",
        "ol_edition_count",
        "ol_current_edition_count",
        "ol_edition_snapshot",
        "identity_status",
        "project_work_id",
        "wikidata_decision",
        "wikidata_qid",
        "openalex_display_candidate_count",
        "openalex_quality_flag",
        "openalex_count_source",
        "openalex_count_unit_id",
        "openalex_measurement_status",
        "openalex_qa_note",
    ]

    output = []

    for r in source:
        status = r["openalex_measurement_status"]
        wid = r["current_ol_work_id"]
        count = ""
        origin = ""
        unit = ""

        if status == "OPERATIONAL_CANDIDATE_COUNT":
            count = r["openalex_candidate_pairs"].strip()
            if not count or not count.isdecimal():
                raise ValueError(f"Invalid mapped count: {wid}")

            flag = "PROVISIONAL"
            origin = "INTEGRATED_PROJECT_W_V1"
            unit = r["project_work_id"]
            note = "暫定候補ペア数。検証済みの学術的言及数ではありません。"

        elif status == "NOT_MAPPED_TO_PROJECT_W":
            assert not r["openalex_candidate_pairs"].strip()
            anchor = anchors.get(wid)

            if anchor and oa_by_anchor.get(anchor):
                count = str(len(oa_by_anchor[anchor]))
                flag = "PROVISIONAL_UNRESOLVED"
                origin = "UNRESOLVED_CALIBRATION_A12_V3"
                unit = anchor
                note = (
                    "作品同定が未確定。較正データ内の著者一致付き候補。"
                    "統合集計と直接比較できません。"
                )
            else:
                flag = "NOT_AVAILABLE"
                origin = "UNRESOLVED_NO_CALIBRATION_COUNT"
                unit = anchor or ""
                note = "未接続で候補数を提供できません。0件ではありません。"

        elif status == "HOLD_OVERAGGREGATED_SOURCE":
            assert not r["openalex_candidate_pairs"].strip()
            flag = "IDENTITY_HOLD"
            note = "作品の過剰統合により集計保留。0件ではありません。"

        else:
            raise ValueError(f"Unexpected status: {status}")

        output.append({
            "ol_work_id": r["historical_ol_work_id"],
            "current_ol_work_id": wid,
            "ol_title": r["ol_source_title"],
            "ol_author_name": r["ol_author_names_display"],
            "ol_first_publish_year": r["ol_source_first_publish_year"],
            "ol_edition_count":
                r["ol_20260228_historical_edition_count"],
            "ol_current_edition_count":
                r["ol_20260228_current_edition_count"],
            "ol_edition_snapshot": "2026-02-28",
            "identity_status": r["identity_status"],
            "project_work_id": r["project_work_id"],
            "wikidata_decision": r["wikidata_effective_decision"],
            "wikidata_qid": r["wikidata_effective_qid"],
            "openalex_display_candidate_count": count,
            "openalex_quality_flag": flag,
            "openalex_count_source": origin,
            "openalex_count_unit_id": unit,
            "openalex_measurement_status": status,
            "openalex_qa_note": note,
        })

    counts = Counter(r["openalex_quality_flag"] for r in output)

    assert len(output) == 34789
    assert counts["PROVISIONAL"] == 32689
    assert counts["IDENTITY_HOLD"] == 17
    assert (
        counts["PROVISIONAL_UNRESOLVED"]
        + counts["NOT_AVAILABLE"]
    ) == 2083

    assert sum(int(r["ol_edition_count"]) for r in output) == 420036

    OUTDIR.mkdir(parents=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=fields, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(output)

    manifest = {
        "status": "LOCAL_REVIEW_ONLY_NOT_PUBLISHED",
        "rows": len(output),
        "columns": len(fields),
        "quality_flags": dict(counts),
        "input_sha256": {
            str(p): sha256(p)
            for p in (SOURCE, MEMBERS, CAL)
        },
        "output_sha256": sha256(OUT),
        "warning": (
            "Provisional counts from different retrieval methods "
            "are not directly comparable; do not sum across OL rows."
        ),
    }

    (OUTDIR / "manifest_v1.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== GENERATED ===")
    print(OUT)
    print("\n=== QUALITY FLAGS ===")
    print(dict(counts))

    # Verify the workshop's intended search experience.
    for term in (
        "Ulysses",
        "Great Gatsby",
        "News from Nowhere",
        "Looking Backward",
    ):
        results = [
            r for r in output
            if term.casefold() in r["ol_title"].casefold()
        ]
        results.sort(
            key=lambda r: int(r["ol_edition_count"]),
            reverse=True,
        )
        print(f"\n=== SEARCH: {term} ({len(results)} OL rows) ===")
        for r in results[:8]:
            print(
                r["ol_work_id"],
                "Editions:", r["ol_edition_count"],
                "OA:", r["openalex_display_candidate_count"] or "(NA)",
                "Flag:", r["openalex_quality_flag"],
                "|", r["ol_title"][:75],
            )

    print("\nREVIEW ONLY — NO GITHUB PUBLICATION")


if __name__ == "__main__":
    main()
