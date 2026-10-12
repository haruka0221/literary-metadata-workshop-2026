#!/usr/bin/env python3
"""Prepare reproducible OL Edition extraction targets."""

import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RESEARCH = Path.home() / "canon-pipeline-openalex-a2val"
SOURCE = RESEARCH / "derived/identity/openlibrary_analysis_targets_v1.tsv"
DEST = Path.home() / "workshop-20261016/data_sources/ol_edition_target_set_v1"

MAP_COLUMNS = [
    "historical_entity_id",
    "historical_ol_work_id",
    "current_entity_id",
    "current_ol_work_id",
    "target_resolution",
]

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

if DEST.exists():
    raise FileExistsError(f"Refusing to overwrite: {DEST}")

with SOURCE.open(encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f, delimiter="\t")
    assert set(MAP_COLUMNS) <= set(reader.fieldnames)
    rows = list(reader)

historical = [r["historical_ol_work_id"] for r in rows]
current = [r["current_ol_work_id"] for r in rows]

assert len(rows) == 34789
assert len(set(historical)) == 34789
assert len(set(current)) == 34789

targets = set(historical) | set(current)

assert all(re.fullmatch(r"OL[0-9]+W", x) for x in targets)

corrections = {
    (r["historical_ol_work_id"], r["current_ol_work_id"])
    for r in rows
    if r["historical_ol_work_id"] != r["current_ol_work_id"]
}

expected_corrections = {
    ("OL9056552W", "OL245401W"),
    ("OL15345521W", "OL509889W"),
    ("OL15062619W", "OL85892W"),
}

assert corrections == expected_corrections
assert len(targets) == 34792

# All validation happens before output creation.
partial = DEST.parent / ".ol_edition_target_set_v1.incomplete"

if partial.exists():
    raise FileExistsError(partial)

partial.mkdir()

target_file = partial / "ol_edition_work_ids_v1.txt"
target_file.write_text(
    "".join(f"{wid}\n" for wid in sorted(targets)),
    encoding="utf-8",
)

map_file = partial / "historical_current_target_map_v1.tsv"

with map_file.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f, fieldnames=MAP_COLUMNS,
        delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(
        {k: r[k] for k in MAP_COLUMNS}
        for r in rows
    )

commit = subprocess.check_output(
    ["git", "-C", str(RESEARCH), "rev-parse", "HEAD"],
    text=True,
).strip()

manifest = {
    "status": "TARGET_SET_PREPARED_NOT_SCANNED",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "research_commit": commit,
    "source_target_map": str(SOURCE),
    "source_target_map_sha256": sha256(SOURCE),
    "historical_target_rows": len(rows),
    "historical_unique_ids": len(set(historical)),
    "current_unique_ids": len(set(current)),
    "corrected_target_count": len(corrections),
    "extraction_target_unique_ids": len(targets),
    "target_file_sha256": sha256(target_file),
    "projection_map_sha256": sha256(map_file),
    "target_policy": "UNION_HISTORICAL_AND_CURRENT_OL_WORK_IDS",
    "interpretation": (
        "Source Work targets only; no conceptual-work identity "
        "or Edition-link correction is asserted."
    ),
}

(partial / "manifest_v1.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

partial.rename(DEST)

print(json.dumps(manifest, ensure_ascii=False, indent=2))
