#!/usr/bin/env python3
"""Read-only, fail-closed identity/Wikidata/OpenAlex workshop join preflight.

No output file is written. This only checks the frozen 2026-10-12
source schemas, keys, identity holds, and historical-target corrections.

Usage:
  python preflight_workshop_join_v3.py --source-root ~/canon-pipeline-openalex-a2val
"""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

SRC = {
    "targets": "derived/identity/openlibrary_analysis_targets_v1.tsv",
    "entities": "derived/identity/source_entities_v3.tsv",
    "map": "derived/identity/work_identity_map_v7.tsv",
    "works": "derived/identity/project_works_v7.tsv",
    "suspensions": "derived/identity/project_work_identity_suspensions_v1.tsv",
    "wikidata": "derived/wikidata_production/full_34789_v6_20260918/final_resolution_v6_34789.tsv",
    "openalex": "derived/openalex_production/integrated_work_visibility_v1/openalex_visibility_by_project_work_v1.tsv",
    "corrections": "derived/identity/openlibrary_target_corrections_v1.tsv",
}
EXPECTED_ROWS = {
    "targets": 34789, "entities": 49163, "map": 44888,
    "works": 32089, "suspensions": 17, "wikidata": 34789,
    "openalex": 32066, "corrections": 3,
}
EXPECTED_SHA = {
    "works": "d82fd38c9bf246184798add67e90432616bbab5afaaafcf7c32d74861cb760b5",
    "openalex": "8c3e2e1f55dcff2723dfe2ba60d6ff1d768f4d56456ce009ab65c78e5b740826",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_nonblank(frame, col, label):
    require(col in frame.columns, f"{label}: missing column {col}")
    require(frame[col].ne("").all(), f"{label}: empty {col}")
    require(frame[col].is_unique, f"{label}: duplicate {col}")


def require_columns(frame, cols, label):
    missing = set(cols) - set(frame.columns)
    require(not missing, f"{label}: missing columns {sorted(missing)}")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.expanduser().resolve()

    for name, relative in SRC.items():
        require((root / relative).is_file(), f"Missing input: {root / relative}")
    for name, expected in EXPECTED_SHA.items():
        actual = sha256(root / SRC[name])
        require(actual == expected, f"{name}: SHA256 mismatch: {actual}")

    d = {
        name: pd.read_csv(root / relative, sep="\t", dtype=str, keep_default_na=False)
        for name, relative in SRC.items()
    }
    for name, frame in d.items():
        require(len(frame) == EXPECTED_ROWS[name],
                f"{name}: rows {len(frame)} != {EXPECTED_ROWS[name]}")

    t, e, m, w, s, wd, oa, fix = (
        d[k] for k in ("targets", "entities", "map", "works", "suspensions", "wikidata", "openalex", "corrections")
    )
    require_columns(t, ["historical_ol_work_id", "current_ol_work_id", "current_entity_id", "historical_entity_id", "target_resolution", "title", "author_keys", "first_publish_year"], "targets")
    require_columns(e, ["entity_id", "source", "source_namespace", "source_id"], "entities")
    require_columns(m, ["source_entity_id", "project_work_id", "membership_role"], "map")
    require_columns(w, ["project_work_id", "status"], "works")
    require_columns(s, ["suspended_source_entity_id", "project_work_id"], "suspensions")
    require_columns(wd, ["target_id", "title", "author", "decision", "selected_qid"], "wikidata")
    require_columns(oa, ["project_work_id", "total_operational_pairs", "measurement_status"], "openalex")
    require_columns(fix, ["historical_ol_work_id", "corrected_ol_work_id"], "corrections")

    for frame, colname, label in (
        (t, "historical_ol_work_id", "targets"),
        (t, "current_ol_work_id", "targets"),
        (t, "current_entity_id", "targets"),
        (e, "entity_id", "entities"),
        (m, "source_entity_id", "map"),
        (w, "project_work_id", "works"),
        (s, "suspended_source_entity_id", "suspensions"),
        (wd, "target_id", "wikidata"),
        (oa, "project_work_id", "openalex"),
        (fix, "historical_ol_work_id", "corrections"),
    ):
        unique_nonblank(frame, colname, label)

    # Three explicit historical-source corrections: never replace historical IDs.
    changed = t[t.historical_ol_work_id != t.current_ol_work_id]
    require(len(changed) == 3, f"Changed targets: {len(changed)} != 3")
    corr = changed.merge(
        fix[["historical_ol_work_id", "corrected_ol_work_id"]],
        on="historical_ol_work_id", how="outer", validate="one_to_one", indicator=True,
    )
    require(corr._merge.eq("both").all(), "Corrections not a 1:1 match to changed targets")
    require(corr.current_ol_work_id.eq(corr.corrected_ol_work_id).all(),
            "Current target IDs disagree with corrections release")

    # Current source-entity references are authoritative; registry is used for QC.
    r = t.merge(
        e[["entity_id", "source", "source_namespace", "source_id"]],
        left_on="current_entity_id", right_on="entity_id", how="left", validate="one_to_one", indicator=True,
    )
    require(r._merge.eq("both").all(), "Some current OL source E are absent from registry")
    require((r.source == "openlibrary").all() and (r.source_namespace == "work").all(),
            "At least one current E is not an Open Library Work")
    require(r.source_id.eq(r.current_ol_work_id).all(), "Current OL ID != source registry ID")
    r = r.drop(columns=["entity_id", "source", "source_namespace", "source_id", "_merge"])

    # Only explicitly current-analysis-target membership is valid here.
    current_map = m[m.membership_role == "current_analysis_target"].copy()
    r = r.merge(
        current_map[["source_entity_id", "project_work_id"]],
        left_on="current_entity_id", right_on="source_entity_id",
        how="left", validate="one_to_one",
    )
    mapped = r.project_work_id.notna() & r.project_work_id.ne("")
    held = r.current_entity_id.isin(s.suspended_source_entity_id)
    require(not (mapped & held).any(), "Suspended source E erroneously mapped to W")
    require(int(mapped.sum()) == 32689, f"Mapped targets: {mapped.sum()} != 32689")
    require(int(held.sum()) == 17, f"Held targets: {held.sum()} != 17")
    require(int((~mapped & ~held).sum()) == 2083, "Unresolved target count != 2083")

    r = r.merge(
        w[["project_work_id", "status"]].rename(columns={"status": "project_work_status"}),
        on="project_work_id", how="left", validate="many_to_one",
    )
    require(r.loc[mapped, "project_work_status"].eq("active").all(),
            "Mapped OL target belongs to a non-active or missing Project W")
    r["identity_status"] = "UNRESOLVED_SOURCE"
    r.loc[mapped, "identity_status"] = "ACTIVE_MAPPED"
    r.loc[held, "identity_status"] = "HOLD_OVERAGGREGATED_SOURCE"

    # Wikidata v6 target_id is historical OL ID, not corrected current OL ID.
    r = r.merge(
        wd[["target_id", "title", "author", "decision", "selected_qid"]].rename(columns={
            "title": "wikidata_historical_title", "author": "wikidata_historical_author",
            "decision": "wikidata_raw_decision", "selected_qid": "wikidata_raw_qid",
        }),
        left_on="historical_ol_work_id", right_on="target_id", how="left",
        validate="one_to_one", indicator="_wd_merge",
    )
    require(r._wd_merge.eq("both").all(), "Wikidata did not match every historical target")
    raw_decisions = r.wikidata_raw_decision.value_counts().to_dict()
    require(raw_decisions == {"MATCH": 8442, "AMBIGUOUS": 358, "NO_MATCH": 25989},
            f"Wikidata raw decision counts changed: {raw_decisions}")
    # A QID in an AMBIGUOUS row is a recorded candidate, NOT an accepted match.
    # Frozen v6 has 357 AMBIGUOUS rows with selected_qid and one without.
    require(r.loc[r.wikidata_raw_decision == "MATCH", "wikidata_raw_qid"].ne("").all(),
            "MATCH Wikidata record lacks selected_qid")
    require(r.loc[r.wikidata_raw_decision == "NO_MATCH", "wikidata_raw_qid"].eq("").all(),
            "NO_MATCH Wikidata record unexpectedly has selected_qid")
    ambiguous = r.wikidata_raw_decision.eq("AMBIGUOUS")
    require(int((ambiguous & r.wikidata_raw_qid.ne("")).sum()) == 357,
            "Expected 357 AMBIGUOUS records with candidate selected_qid")
    require(int((ambiguous & r.wikidata_raw_qid.eq("")).sum()) == 1,
            "Expected one AMBIGUOUS record without selected_qid")
    r["wikidata_effective_decision"] = r.wikidata_raw_decision
    # Only unequivocal MATCH is eligible to populate an effective Wikidata QID.
    r["wikidata_effective_qid"] = r.wikidata_raw_qid.where(
        r.wikidata_raw_decision.eq("MATCH"), ""
    )
    correction_mask = r.historical_ol_work_id != r.current_ol_work_id
    r.loc[correction_mask, "wikidata_effective_decision"] = "HOLD_TARGET_CORRECTION"
    r.loc[correction_mask, "wikidata_effective_qid"] = ""
    require(int(correction_mask.sum()) == 3, "Correction hold did not affect exactly three rows")
    require(r.loc[r.wikidata_effective_decision != "MATCH", "wikidata_effective_qid"].eq("").all(),
            "A non-MATCH/held Wikidata QID was promoted to effective QID")
    require(r.loc[r.wikidata_effective_decision == "MATCH", "wikidata_effective_qid"].ne("").all(),
            "An effective MATCH lacks a QID")

    # OpenAlex measures belong to active project W, not historic OL record.
    r = r.merge(
        oa[["project_work_id", "total_operational_pairs", "measurement_status"]],
        on="project_work_id", how="left", validate="many_to_one", indicator="_oa_merge",
    )
    require(r.loc[mapped, "_oa_merge"].eq("both").all(), "Missing OpenAlex row for active mapped W")
    require(r.loc[~mapped, "_oa_merge"].eq("left_only").all(), "Unmapped OL target has OpenAlex W row")
    r["openalex_measurement_status"] = r["measurement_status"].fillna("")
    r.loc[r.identity_status == "UNRESOLVED_SOURCE", "openalex_measurement_status"] = "NOT_MAPPED_TO_PROJECT_W"
    r.loc[r.identity_status == "HOLD_OVERAGGREGATED_SOURCE", "openalex_measurement_status"] = "HOLD_OVERAGGREGATED_SOURCE"
    r["openalex_candidate_pairs"] = r.total_operational_pairs.fillna("")
    r.loc[~mapped, "openalex_candidate_pairs"] = ""
    require(r.loc[~mapped, "openalex_candidate_pairs"].eq("").all(),
            "OpenAlex count leaked onto unresolved/held sources")
    require(r.loc[mapped, "openalex_measurement_status"].ne("").all(),
            "Missing measurement status for mapped W")
    nonblank_counts = r.loc[mapped, "openalex_candidate_pairs"]
    require(nonblank_counts.str.fullmatch(r"\d+").all(),
            "A mapped W has non-integer/NA candidate count; review measurement semantics")

    summary = {
        "status": "PREFLIGHT_PASSED_NO_FILES_WRITTEN",
        "source_root": str(root),
        "source_rows": {name: len(frame) for name, frame in d.items()},
        "join_rows": len(r),
        "unique_historical_ol_ids": r.historical_ol_work_id.nunique(),
        "identity_status": r.identity_status.value_counts().to_dict(),
        "wikidata_raw_decision": raw_decisions,
        "wikidata_ambiguous_raw_qid_present": int((ambiguous & r.wikidata_raw_qid.ne("")).sum()),
        "wikidata_ambiguous_raw_qid_missing": int((ambiguous & r.wikidata_raw_qid.eq("")).sum()),
        "wikidata_effective_decision": r.wikidata_effective_decision.value_counts().to_dict(),
        "wikidata_effective_qid_nonempty": int(r.wikidata_effective_qid.ne("").sum()),
        "wikidata_held_corrections": r.loc[correction_mask, [
            "historical_ol_work_id", "current_ol_work_id", "wikidata_raw_decision",
            "wikidata_raw_qid", "wikidata_effective_decision", "wikidata_effective_qid",
        ]].to_dict("records"),
        "mapped_project_w_unique": r.loc[mapped, "project_work_id"].nunique(),
        "openalex_measurement_status": r.openalex_measurement_status.value_counts().to_dict(),
        "openalex_nonempty_counts_on_unmapped": int(r.loc[~mapped, "openalex_candidate_pairs"].ne("").sum()),
        "note": "OpenAlex W counts may repeat across several OL source rows; never sum them across rows.",
    }
    require(len(r) == 34789, "Join changed historical OL target row count")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
