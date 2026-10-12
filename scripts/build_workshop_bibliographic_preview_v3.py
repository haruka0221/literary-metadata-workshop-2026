#!/usr/bin/env python3
"""Make a new, unpublished bibliographic preview from the audited core v1 CSV.

Adds source-native Open Library Work -> Author names (frozen 2026-02-28
source layer) and historical-OL-target edition counts. Does not change the
core preview, frozen research artifacts, or Git history. Fails closed on
unexpected schema/key/coverage and refuses to overwrite an existing output.

Usage:
 python ~/workshop-20261016/scripts/build_workshop_bibliographic_preview_v3.py \
   --source-root ~/canon-pipeline-openalex-a2val
"""

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

CORE_BASENAME = "ol_wikidata_openalex_core_preview_v1.csv"
CORE_SHA256 = "f564edc80fd49e6ca99a5b75dee0cc64cddea887c990b51b5b7736fbd52722f5"
OUTPUT_BASENAME = "ol_wikidata_openalex_bibliographic_preview_v3.csv"
QC_BASENAME = "ol_wikidata_openalex_bibliographic_preview_v3_qc.json"
SOURCES = {
    "author_links": "derived/openlibrary_author_source_v1/openlibrary_current_work_authors_v1.tsv",
    "author_names": "derived/openlibrary_author_source_v1/openlibrary_author_names_v1.tsv",
    "edition_counts": "derived/ol_edition_counts.tsv",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for buf in iter(lambda: f.read(1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()


def read_tsv(path):
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)


def read_csv(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def author_summary(group):
    # Preserve ALL source author edges. Primary/name_type=name names alone are
    # displayed; source IDs remain available even when name records are absent.
    group = group.copy()
    group["_ord"] = pd.to_numeric(group["author_ordinal"], errors="coerce")
    # Source author ordinal may be missing/irregular. Preserve original row
    # order as stable tie-breaker instead of inventing a rank.
    group = group.sort_values(["_ord", "_row"], na_position="last", kind="stable")
    values = []
    for row in group.itertuples(index=False):
        # Access columns by name with pandas-safe column identifiers.
        values.append({
            "ordinal": row.author_ordinal if row.author_ordinal else None,
            "author_id": row.author_source_id if row.author_source_id else None,
            "name": row.name_value if row.name_value else None,
            # Preserve missing/invalid source edges without fabricating authors.
            "edge_parse_status": row.author_edge_parse_status,
            "name_resolution": (
                "AUTHOR_KEY_MISSING" if not row.author_source_key
                else "NAME_FOUND" if row.name_value
                else "NAME_UNAVAILABLE"
            ),
        })
    missing = sum(x["name"] is None for x in values)
    status = ("ALL_NAMES_FOUND" if missing == 0 else
              "ALL_NAMES_MISSING" if missing == len(values) else
              "PARTIAL_NAMES_MISSING")
    return {
        "ol_author_names_display": " | ".join(x["name"] for x in values if x["name"] is not None),
        "ol_author_evidence_json": json.dumps(values, ensure_ascii=False, separators=(",", ":")),
        "ol_author_link_count": str(len(values)),
        "ol_author_name_status": status,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--preview-dir", type=Path, default=Path.home() / "workshop-20261016" / "previews")
    args = p.parse_args()
    root = args.source_root.expanduser().resolve()
    outdir = args.preview_dir.expanduser().resolve()
    require(outdir != root and root not in outdir.parents,
            "Output must be outside the research checkout")
    core_path = outdir / CORE_BASENAME
    csv_path = outdir / OUTPUT_BASENAME
    qc_path = outdir / QC_BASENAME
    require(core_path.is_file(), f"Core preview missing: {core_path}")
    require(not csv_path.exists() and not qc_path.exists(),
            "One of the v3 output paths already exists; refusing overwrite")
    require(sha256(core_path) == CORE_SHA256,
            "Core preview SHA256 differs from audited v1; no output written")
    for label, rel in SOURCES.items():
        require((root / rel).is_file(), f"Source not found ({label}): {root / rel}")

    core = read_csv(core_path)
    links = read_tsv(root / SOURCES["author_links"])
    names = read_tsv(root / SOURCES["author_names"])
    ed = read_tsv(root / SOURCES["edition_counts"])

    expected_core_cols = {"historical_ol_work_id", "current_ol_work_id", "ol_source_title",
                          "identity_status", "project_work_id", "wikidata_effective_decision",
                          "openalex_candidate_pairs"}
    require(expected_core_cols <= set(core.columns), "Unexpected core v1 schema")
    require(len(core) == 34789 and core.historical_ol_work_id.is_unique,
            "Core historical target spine invalid")
    require(core.current_ol_work_id.is_unique, "Core current OL keys are not unique")

    # Edition file is keyed to HISTORICAL Work IDs, not corrected Work IDs.
    require(set(["work_key", "edition_count"]) <= set(ed.columns), "Unexpected edition schema")
    require(len(ed) == 34789 and ed.work_key.is_unique, "Edition file key cardinality changed")
    ed["historical_ol_work_id"] = ed.work_key.str.replace(r"^/works/", "", regex=True)
    require(ed.historical_ol_work_id.is_unique, "Duplicate stripped edition IDs")
    require(set(ed.historical_ol_work_id) == set(core.historical_ol_work_id),
            "Edition Work IDs do not match the historical target population")
    numeric_ed = pd.to_numeric(ed.edition_count, errors="coerce")
    require(numeric_ed.notna().all() and numeric_ed.ge(1).all() and (numeric_ed % 1 == 0).all(),
            "Edition counts contain missing/negative/nonintegral values")
    r = core.merge(ed[["historical_ol_work_id", "edition_count"]],
                   on="historical_ol_work_id", how="left", validate="one_to_one")
    r = r.rename(columns={"edition_count": "ol_historical_work_edition_count"})
    corrected = r.historical_ol_work_id.ne(r.current_ol_work_id)
    require(int(corrected.sum()) == 3, "Unexpected number of corrected OL targets")
    r["ol_current_work_edition_count"] = r.ol_historical_work_edition_count.where(~corrected, "")
    r["ol_edition_count_status"] = "CURRENT_ID_EQUALS_HISTORICAL"
    r.loc[corrected, "ol_edition_count_status"] = "HOLD_TARGET_CORRECTION"
    r["ol_edition_count_source"] = SOURCES["edition_counts"]
    r["ol_edition_count_snapshot_status"] = "SOURCE_OBSERVATION_DATE_UNVERIFIED"

    # Native OL Work-author edges are keyed to CURRENT Work IDs.
    expected_link_cols = {"current_ol_work_id", "author_ordinal", "author_source_key", "author_source_id", "author_edge_parse_status"}
    expected_name_cols = {"author_source_key", "name_type", "name_value"}
    require(expected_link_cols <= set(links.columns), "Unexpected author-link schema")
    require(expected_name_cols <= set(names.columns), "Unexpected author-name schema")
    require(len(links) == 37652, "Unexpected author edge count")
    require(links.current_ol_work_id.nunique() == 34435, "Unexpected linked-work count")
    require(set(links.current_ol_work_id) <= set(core.current_ol_work_id),
            "Author links contain Work IDs outside current targets")
    # Frozen Open Library source has precisely two malformed author-role
    # entries containing no `author` key. They are SOURCE EVIDENCE, not authors.
    # Keep those rows in JSON evidence and include them in the edge counts.
    blank_key = links.author_source_key.eq("")
    require(int(blank_key.sum()) == 2, "Unexpected number of blank Author keys")
    require(links.loc[blank_key, "author_source_id"].eq("").all(),
            "Blank Author key accompanied by a nonblank Author ID")
    require(links.loc[blank_key, "author_edge_parse_status"].eq("author_key_missing").all(),
            "Unexpected parse status on missing-key author entries")
    require(set(links.loc[blank_key, "current_ol_work_id"]) == {"OL3335245W", "OL731644W"},
            "Missing-key author entries moved to unexpected Works")
    # Do not count the blank key itself as a fourth missing Author ID.
    identified_author_keys = set(links.loc[~blank_key, "author_source_key"])
    require(len(identified_author_keys) == 16405, "Unique nonblank Author IDs changed")
    names = names.loc[names.name_type.eq("name"), ["author_source_key", "name_value"]].copy()
    require(len(names) == 16402 and names.author_source_key.is_unique and names.name_value.ne("").all(),
            "Name-type=name records unexpectedly changed")
    missing_name_keys = identified_author_keys - set(names.author_source_key)
    require(missing_name_keys == {
        "/authors/OL6789084A", "/authors/OL6817526A", "/authors/OL9258086A"
    }, "Author IDs without a name record changed")
    joined = links.merge(names, on="author_source_key", how="left", validate="many_to_one")
    joined["name_value"] = joined.name_value.fillna("")
    joined["_row"] = range(len(joined))
    summaries = []
    for work_id, group in joined.groupby("current_ol_work_id", sort=False):
        summaries.append({"current_ol_work_id": work_id, **author_summary(group)})
    author_df = pd.DataFrame(summaries)
    require(len(author_df) == 34435 and author_df.current_ol_work_id.is_unique,
            "Work-author aggregation unexpectedly changed")
    r = r.merge(author_df, on="current_ol_work_id", how="left", validate="one_to_one")
    for field in ("ol_author_names_display", "ol_author_evidence_json", "ol_author_link_count"):
        r[field] = r[field].fillna("")
    r["ol_author_name_status"] = r.ol_author_name_status.fillna("NO_AUTHOR_LINK")
    r["ol_author_source_snapshot"] = "2026-02-28"
    r["ol_author_source_release"] = "openlibrary-author-source-v1"

    # QC before file writes. Do not sum candidate counts across OL rows.
    require(len(r) == 34789 and r.historical_ol_work_id.is_unique,
            "Final row-count/uniqueness violated")
    require(int(r.ol_author_name_status.eq("NO_AUTHOR_LINK").sum()) == 354,
            "Missing-author Work count differs from frozen source")
    require(int(r.ol_author_link_count.replace("", "0").astype(int).gt(1).sum()) == 1730,
            "Multi-author edge count differs from frozen source")
    require(r.loc[corrected, "ol_current_work_edition_count"].eq("").all(),
            "Historical edition counts promoted to corrected Work")
    require(r.loc[~corrected, "ol_current_work_edition_count"].ne("").all(),
            "Edition count missing for unchanged Work")
    require(r.loc[r.wikidata_effective_decision.ne("MATCH"), "wikidata_effective_qid"].eq("").all(),
            "Unaccepted Wikidata QID leaked into effective result")
    require(r.loc[r.identity_status.ne("ACTIVE_MAPPED"), "openalex_candidate_pairs"].eq("").all(),
            "Unmapped W has an OpenAlex candidate count")
    require(r.loc[corrected, "wikidata_effective_decision"].eq("HOLD_TARGET_CORRECTION").all(),
            "Corrected historical Wikidata target was not held")

    outdir.mkdir(parents=True, exist_ok=True)
    with csv_path.open("x", newline="", encoding="utf-8-sig") as f:
        r.to_csv(f, index=False)
    report = {
        "status": "BIBLIOGRAPHIC_PREVIEW_WRITTEN_NOT_PUBLISHED",
        "preview_csv": str(csv_path),
        "rows": len(r),
        "unique_historical_ol_ids": r.historical_ol_work_id.nunique(),
        "author_status": r.ol_author_name_status.value_counts().to_dict(),
        "works_with_multiple_author_edges": int(r.ol_author_link_count.replace("", "0").astype(int).gt(1).sum()),
        "author_edges_total": len(links),
        "author_edges_without_key": int(blank_key.sum()),
        "author_works_with_keyless_edge": sorted(links.loc[blank_key, "current_ol_work_id"].tolist()),
        "unique_nonblank_author_ids": len(identified_author_keys),
        "author_ids_without_name_record": sorted(missing_name_keys),
        "edition_status": r.ol_edition_count_status.value_counts().to_dict(),
        "corrected_edition_hold_ids": r.loc[corrected, "current_ol_work_id"].tolist(),
        "core_preview_sha256": sha256(core_path),
        "source_sha256": {key: sha256(root / rel) for key, rel in SOURCES.items()},
        "preview_sha256": sha256(csv_path),
        "limitations": [
            "Not published; authors reflect Open Library source records, not verified literary authorship",
            "Author names are name_type=name; author ordinals, IDs, and missing-key edge statuses retained in JSON evidence",
            "Historical edition counts refer to historical OL Work keys, not merged conceptual Project W",
            "Historical edition-count observation date not yet verified",
            "Edition count for corrected/current targets is withheld until independently sourced",
            "OpenAlex counts are provisional target-reference pairs and repeat across OL rows mapped to one Project W",
        ],
    }
    with qc_path.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({k: report[k] for k in (
        "status", "preview_csv", "rows", "unique_historical_ol_ids",
        "author_status", "works_with_multiple_author_edges", "author_edges_without_key", "edition_status",
        "corrected_edition_hold_ids", "preview_sha256")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
