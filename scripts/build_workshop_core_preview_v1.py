#!/usr/bin/env python3
"""Export an audited CORE PREVIEW (not the finished workshop dataset).

Requires preflight_workshop_join_v3.py alongside this script.  Reads frozen
canon-pipeline artifacts; writes only into a separate, non-repository preview
folder.  Does not resolve authors' names, edition counts or edition histories.

Example:
  python ~/workshop-20261016/scripts/build_workshop_core_preview_v1.py \
      --source-root ~/canon-pipeline-openalex-a2val
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

PREVIEW_NAME = "ol_wikidata_openalex_core_preview_v1.csv"
QC_NAME = "ol_wikidata_openalex_core_preview_v1_qc.json"

SOURCES = {
    "targets": "derived/identity/openlibrary_analysis_targets_v1.tsv",
    "map": "derived/identity/work_identity_map_v7.tsv",
    "works": "derived/identity/project_works_v7.tsv",
    "suspensions": "derived/identity/project_work_identity_suspensions_v1.tsv",
    "wikidata": "derived/wikidata_production/full_34789_v6_20260918/final_resolution_v6_34789.tsv",
    "openalex": "derived/openalex_production/integrated_work_visibility_v1/openalex_visibility_by_project_work_v1.tsv",
}
SOURCE_COMMIT = "dd8ee20393297edfd786fdb3566291fceccb475c"


def require(condition, msg):
    if not condition:
        raise ValueError(msg)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda: f.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def read(path):
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, default=Path.home() / "workshop-20261016" / "previews")
    args = p.parse_args()
    root = args.source_root.expanduser().resolve()
    out = args.output_dir.expanduser().resolve()
    require(out != root and root not in out.parents,
            "Output directory must be OUTSIDE the research checkout")
    csv_path, qc_path = out / PREVIEW_NAME, out / QC_NAME
    require(not csv_path.exists() and not qc_path.exists(),
            "Preview output already exists; no files will be overwritten")

    # Re-run the actual previously tested safeguards, not an unverified
    # reimplementation of its acceptance conditions.
    preflight_script = Path(__file__).resolve().with_name("preflight_workshop_join_v3.py")
    require(preflight_script.is_file(), f"Missing required preflight: {preflight_script}")
    completed = subprocess.run(
        [sys.executable, str(preflight_script), "--source-root", str(root)],
        text=True, capture_output=True, check=True,
    )
    preflight = json.loads(completed.stdout)
    require(preflight.get("status") == "PREFLIGHT_PASSED_NO_FILES_WRITTEN",
            "Preflight did not report success")

    t, m, w, s, wd, oa = (read(root / SOURCES[k]) for k in
                          ("targets", "map", "works", "suspensions", "wikidata", "openalex"))

    r = t[["historical_ol_work_id", "current_ol_work_id",
           "historical_entity_id", "current_entity_id", "target_resolution",
           "title", "author_keys", "first_publish_year"]].copy()
    r = r.rename(columns={
        "title": "ol_source_title",
        "author_keys": "ol_author_keys",
        "first_publish_year": "ol_source_first_publish_year",
    })
    current_map = m[m.membership_role.eq("current_analysis_target")]
    r = r.merge(
        current_map[["source_entity_id", "project_work_id"]],
        left_on="current_entity_id", right_on="source_entity_id",
        how="left", validate="one_to_one",
    ).drop(columns="source_entity_id")
    mapped = r.project_work_id.notna() & r.project_work_id.ne("")
    held = r.current_entity_id.isin(s.suspended_source_entity_id)
    r["identity_status"] = "UNRESOLVED_SOURCE"
    r.loc[mapped, "identity_status"] = "ACTIVE_MAPPED"
    r.loc[held, "identity_status"] = "HOLD_OVERAGGREGATED_SOURCE"

    r = r.merge(
        w[["project_work_id", "status"]].rename(columns={"status": "project_work_status"}),
        on="project_work_id", how="left", validate="many_to_one",
    )

    # `target_id` belongs to the historical OL target. Retain the historical
    # candidate QID, but NEVER promote AMBIGUOUS or corrected-target QIDs.
    r = r.merge(
        wd[["target_id", "title", "author", "decision", "selected_qid"]].rename(columns={
            "title": "wikidata_historical_target_title",
            "author": "wikidata_historical_target_author",
            "decision": "wikidata_raw_decision",
            "selected_qid": "wikidata_raw_candidate_qid",
        }),
        left_on="historical_ol_work_id", right_on="target_id",
        how="left", validate="one_to_one",
    ).drop(columns="target_id")
    r["wikidata_effective_decision"] = r.wikidata_raw_decision
    r["wikidata_effective_qid"] = r.wikidata_raw_candidate_qid.where(
        r.wikidata_raw_decision.eq("MATCH"), ""
    )
    correction = r.historical_ol_work_id.ne(r.current_ol_work_id)
    r.loc[correction, "wikidata_effective_decision"] = "HOLD_TARGET_CORRECTION"
    r.loc[correction, "wikidata_effective_qid"] = ""

    r = r.merge(
        oa[["project_work_id", "total_operational_pairs", "measurement_status"]],
        on="project_work_id", how="left", validate="many_to_one",
    )
    r["openalex_candidate_pairs"] = r.total_operational_pairs.fillna("")
    r.loc[~mapped, "openalex_candidate_pairs"] = ""
    r["openalex_measurement_status"] = r.measurement_status.fillna("")
    r.loc[r.identity_status.eq("UNRESOLVED_SOURCE"),
          "openalex_measurement_status"] = "NOT_MAPPED_TO_PROJECT_W"
    r.loc[r.identity_status.eq("HOLD_OVERAGGREGATED_SOURCE"),
          "openalex_measurement_status"] = "HOLD_OVERAGGREGATED_SOURCE"

    # All checks happen BEFORE the first file write.
    require(len(r) == 34789 and r.historical_ol_work_id.is_unique,
            "Historical OL row spine is not 34,789 unique targets")
    require(r.identity_status.value_counts().to_dict() == {
        "ACTIVE_MAPPED": 32689,
        "UNRESOLVED_SOURCE": 2083,
        "HOLD_OVERAGGREGATED_SOURCE": 17,
    }, "Unexpected identity status counts")
    require(int(r.loc[mapped, "project_work_id"].nunique()) == 32065,
            "Unexpected unique mapped Project W count")
    require(r.wikidata_effective_decision.value_counts().to_dict() == {
        "MATCH": 8441, "AMBIGUOUS": 358,
        "NO_MATCH": 25987, "HOLD_TARGET_CORRECTION": 3,
    }, "Unexpected effective Wikidata statuses")
    require(r.loc[r.wikidata_effective_decision.ne("MATCH"),
                  "wikidata_effective_qid"].eq("").all(),
            "Unaccepted/held Wikidata QID leaked into effective QID")
    require(r.loc[~mapped, "openalex_candidate_pairs"].eq("").all(),
            "OpenAlex values leaked to unresolved/held rows")
    require(r.loc[mapped, "openalex_candidate_pairs"].str.fullmatch(r"\d+").all(),
            "Unexpected OpenAlex count on a mapped W")
    require(r.loc[mapped, "project_work_status"].eq("active").all(),
            "A mapped Project W is not active")

    r["identity_version"] = "project_works_v7"
    r["wikidata_version"] = "full_34789_v6_20260918"
    r["openalex_version"] = "integrated_work_visibility_v1_PROVISIONAL_OPERATIONAL"
    r["source_commit"] = SOURCE_COMMIT
    cols = [
        "historical_ol_work_id", "current_ol_work_id", "historical_entity_id",
        "current_entity_id", "target_resolution", "ol_source_title",
        "ol_author_keys", "ol_source_first_publish_year", "project_work_id",
        "project_work_status", "identity_status",
        "wikidata_historical_target_title", "wikidata_historical_target_author",
        "wikidata_raw_decision", "wikidata_raw_candidate_qid",
        "wikidata_effective_decision", "wikidata_effective_qid",
        "openalex_candidate_pairs", "openalex_measurement_status",
        "identity_version", "wikidata_version", "openalex_version", "source_commit",
    ]
    r = r[cols].fillna("")

    out.mkdir(parents=True, exist_ok=True)
    # Fail closed: never overwrite a prior preview.
    with csv_path.open("x", encoding="utf-8-sig", newline="") as stream:
        r.to_csv(stream, index=False)
    report = {
        "status": "CORE_PREVIEW_WRITTEN_NOT_PUBLISHED",
        "preview_csv": str(csv_path),
        "rows": len(r),
        "columns": cols,
        "unique_historical_ol_ids": r.historical_ol_work_id.nunique(),
        "mapped_project_w_unique": r.loc[mapped, "project_work_id"].nunique(),
        "identity_status": r.identity_status.value_counts().to_dict(),
        "wikidata_effective_decision": r.wikidata_effective_decision.value_counts().to_dict(),
        "openalex_measurement_status": r.openalex_measurement_status.value_counts().to_dict(),
        "source_commit": SOURCE_COMMIT,
        "source_sha256": {k: sha256(root / path) for k, path in SOURCES.items()},
        "preview_sha256": sha256(csv_path),
        "limitations": [
            "PREVIEW ONLY; does not supply validated author names or edition counts",
            "OL first_publish_year is source-reported historical evidence, not definitive original publication year",
            "Wikidata historical target author/QID are evidence, not authoritative authorship/current match",
            "OpenAlex is provisional W x OpenAlex Work candidate pairs, not confirmed citations",
            "OpenAlex counts repeat when several OL source records map to one project W",
            "Restored source-light Alcott W is absent from the OL source-row projection",
        ],
    }
    with qc_path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    # Keep terminal output short; detailed provenance is in the QC file.
    print(json.dumps({k: report[k] for k in (
        "status", "preview_csv", "rows", "unique_historical_ol_ids",
        "mapped_project_w_unique", "identity_status", "wikidata_effective_decision",
        "openalex_measurement_status", "preview_sha256",
    )}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
