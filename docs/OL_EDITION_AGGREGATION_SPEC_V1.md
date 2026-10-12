# Open Library Edition Extraction and Aggregation Specification v1

Status: PROPOSED
Date: 2026-10-12

## 1. Purpose

Create reusable Edition-level bibliographic evidence and
aggregations from a fixed Open Library Editions dump.

Keep generic extraction and aggregation independent from
the workshop's historical target population.

## 2. Source

Open Library Editions dump: 2026-02-28.

Source file:
 /media/hdd1/user/tsutsui/openlibrary/ol_dump_editions_2026-02-28.txt.gz

Source content SHA256: NOT YET CALCULATED.

Preserve snapshot, source path, source size,
processing code version, output hashes and audit results.

## 3. Target universe

Historical population: 34,789 Open Library source Work records.

Use the union of historical and corrected current OL Work IDs
as the extraction target set. Verify its unique size at runtime.

Do not equate OL Work records with project conceptual W.

## 4. Core outputs

edition_records_v1.jsonl
- One unique Edition record per Edition key
- Preserve full source Edition JSON
- Preserve all source Work links

edition_details_v1.tsv
- edition_key
- edition_title
- publish_date_raw
- publish_year
- publish_year_parse_status
- publishers_json
- publish_places_json
- languages_json
- number_of_pages
- isbn_10_json
- isbn_13_json
- source_snapshot

edition_work_links_v1.tsv
- edition_key
- source_ol_work_id
- work_link_ordinal
- is_extraction_target

work_edition_summary_v1.tsv
- source_ol_work_id
- edition_count
- editions_with_publish_year
- editions_without_publish_year
- editions_with_incomplete_date
- earliest_observed_edition_year
- latest_observed_edition_year
- editions_with_language_metadata
- editions_without_language_metadata
- editions_with_publisher_metadata
- editions_without_publisher_metadata

work_edition_by_decade_v1.tsv
- source_ol_work_id
- decade
- edition_count

work_edition_by_language_v1.tsv
- source_ol_work_id
- language_key
- edition_count

historical_targets_edition_summary_v1.tsv
- historical_ol_work_id
- current_ol_work_id
- target_resolution
- historical_work_edition_count
- current_work_edition_count
- historical_work_earliest_observed_year
- current_work_earliest_observed_year
- source_snapshot

The historical-target summary must contain exactly 34,789 rows.

## 5. Publication date parsing

Preserve the original publish_date string.

Statuses:
- EXACT_YEAR
- ISO_FULL_DATE
- ENGLISH_FULL_DATE
- ENGLISH_MONTH_YEAR
- YEAR_WITH_INVALID_DATE_COMPONENTS
- AMBIGUOUS
- UNPARSEABLE
- MISSING

Use full format validation, not arbitrary four-digit
substring extraction.

Examples:
- 1890 -> 1890 / EXACT_YEAR
- July 2003 -> 2003 / ENGLISH_MONTH_YEAR
- May 18, 2011 -> 2011 / ENGLISH_FULL_DATE
- 1928-01-01 -> 1928 / ISO_FULL_DATE
- 1924/00/00 -> 1924 / YEAR_WITH_INVALID_DATE_COMPONENTS
- 189-? -> null / AMBIGUOUS

Incomplete-date years must remain separately identifiable.

Never interpret observed Edition year as certified
first publication year of a conceptual literary work.

## 6. Aggregation

Count distinct Edition IDs per OL Work.

Preserve all source Work links, including links to
non-target Works in matched Edition records.

A multi-Work Edition contributes once to each linked Work,
but must not be double-counted in global unique-Edition totals.

For a multi-language Edition, count the Edition once
in each explicitly recorded language category.

Language and publisher missingness must be retained.

Do not normalize publisher identities in v1.

Do not restrict Edition publication years to 1880-1950.

## 7. Quality control

Before the full dump scan:
- Validate transformations on existing 779 Edition records.
- Verify Edition uniqueness and link consistency.
- Verify date parsing and missing-value treatment.
- Verify Work-level counts against extracted links.

After the full scan:
- Confirm complete source traversal.
- Confirm output row counts and unique keys.
- Verify Work-to-Edition count invariants.
- Audit historical/current target projection.
- Record output SHA256 hashes and a manifest.
- Do not overwrite existing versioned releases.

Do not publish partially generated outputs.

## 8. Research integration

Workshop repository and research repository remain separate.

Generic extraction/aggregation code may later be transferred
to canon-pipeline through a dedicated branch and review.

Do not modify frozen research artifacts.
