# Leborg Auto-Parser — System Specification

## Overview

The Leborg Auto-Parser is an automated pipeline that monitors government legislation sources, detects changes, parses updated documents into structured CSV, and syncs them to the Leborg platform. A dashboard surfaces results and lets operators manually fix documents that fail automated parsing.

---

## Supported Sources

| Jurisdiction | Parser Module | POC Code | Source | URL / ID Pattern |
|---|---|---|---|---|
| Canada Federal | `ca_xml_parser.py` | [`parse_xml.py`](parse_xml.py) | laws-lois.justice.gc.ca | `https://laws-lois.justice.gc.ca/eng/XML/{ACT}.xml` |
| France | `legifrance_parser.py` | [`fetch_loda.py`](fetch_loda.py) | api.piste.gouv.fr (Legifrance) | Non-codes: `legifrance.gouv.fr/loda/id/{JORFTEXT…}` · Codes: `legifrance.gouv.fr/codes/section_lc/{LEGITEXT…}/{LEGISCTA…}` |

New jurisdictions can be added by providing an ID/URL pattern and a modification-date extraction rule (see [Adding Jurisdictions](#adding-jurisdictions)).

---

## Weekly Sync Pipeline

The pipeline runs once per week for every **activated** parser. The steps below apply to each document in the Leborg DB that is **In Force** or **Published** and matches the jurisdiction's URL/ID pattern.

> **Exclusions (all runs):** Before processing any document, the pipeline checks the tool DB. Documents on the **Exceptions list** or in **Pending review** (status `changes-detected` not yet resolved by an analyst) are skipped entirely for that cycle.

```
┌──────────────┐     ┌─────────────────────┐     ┌──────────────────────────┐
│  Leborg API  │────▶│  Skip exceptions &  │────▶│  Fetch modification      │
│  (doc list)  │     │  pending-review docs│     │  date from gov site      │
└──────────────┘     └─────────────────────┘     └────────────┬─────────────┘
                                                              │
                  ┌───────────────────┬──────────────────────┤
                  │                   │                        │
              Same date         Different date           No date available
                  │                   │                        │
          Mark Current      Fetch sections from         Check Leborg for
                            gov site + Leborg,          existing parsed text
                            compare, upload new         ─────────┬──────────
                            version to Leborg           Has text │ No text
                                                   Pre-parsed   │ Upload
                                                   logic ▼      │ directly
```

### Step-by-step

1. **List documents** — Call the [Leborg List Documents API](https://github.com/Nimonik/leborg/wiki/Leborg-API-V2#list-documents) to retrieve all principal documents that are *In Force* or *Published* and qualify for the active parser's URL/ID pattern.

2. **Apply exclusions** — Remove from the working set any document whose tool-DB record has status `exceptions` or `changes-detected` (pending analyst review). These documents are not processed in this cycle.

3. **Fetch modification date** — Each parser extracts the `modification_date` from the government source using source-specific logic (e.g. HTTP `Last-Modified` header for Canadian XML, `modifDate` field from the Legifrance API).

4. **Compare dates** — Check the fetched modification date against the value stored in the tool DB for that document:

   | Condition | Action |
   |---|---|
   | Dates match | Mark document **Current**. No further action. |
   | Dates differ | Fetch current sections from gov site **and** from Leborg (via [List Legislation Sections API](https://github.com/Nimonik/leborg/wiki/Leborg-API-V2#list-legislation-sections)), run standard comparison logic, upload new version. |
   | No modification date | Check Leborg for existing parsed text. If found: apply **Pre-Parsed Documents logic** (see below). If not found: parse and upload as new. |

5. **Record sync metadata** — After every document check, write to the tool DB:
   - `last_checked_date` (always)
   - `last_modification_date` (only when a new version is created or the document is new)

---

## Pre-Parsed Documents Logic

This logic applies when the pipeline encounters a document that already has parsed text in Leborg (typically during the first run for a given jurisdiction). It runs instead of the standard upload path and uses AI to filter out false-positive changes.

### Detection

When no modification date is available and the [Leborg Check Parsed Text API](https://trello.com/c/XU3Pt10I/3450-leborg-api-to-check-tracked-parsed-status-of-a-legislation) confirms the document already has parsed text, the document is treated as **pre-parsed** and the steps below apply.

### Processing

```
Parse document from gov site
         │
Generate new CSV
         │
Compare new CSV against existing Leborg version
(standard comparison logic + AI to filter false positives)
         │
    ┌────┴────────────────────────────┐
    │                                 │
No changes                    Changes detected
(all sections SAME,           (UPDATED / NEW /
 no NEW or DELETED)            DELETED present)
    │                                 │
Upload to Leborg              Flag for analyst review
automatically                 (status: changes-detected)
                              Pipeline skips on next cycle
```

**No changes detected** — the new CSV matches the existing Leborg version in all sections. The pipeline uploads it to Leborg automatically without human involvement.

**Changes detected** — one or more sections are marked UPDATED, NEW, or DELETED after AI false-positive filtering. The document is set to status `changes-detected` and surfaced in the **Pre-Parsed Review** tab for analyst action.

### AI usage in this flow

AI is used **only** within the pre-parsed documents path to distinguish genuine content changes from differences caused by parsing variations (e.g. whitespace, punctuation normalisation, structural re-numbering). AI is **not** used in the standard pipeline path for documents without prior parsed text.

### Analyst Review actions

When a document is flagged (`changes-detected`), an analyst opens it in the **Pre-Parsed Review** tab and chooses one of three actions:

| Action | When to use | What happens |
|---|---|---|
| **Approve as-is** | Detected changes are real and correct — no false positives | New CSV is uploaded to Leborg; document transitions to standard auto-pipeline from the next cycle onwards |
| **Mark as manually uploaded** | There are false positives that cannot be resolved automatically | Analyst uploads corrected CSV directly in Leborg and manually matches affected clauses to avoid false customer notifications; tool marks the document as resolved (status `updated`) |
| **Add to exceptions** | Changes cannot be reconciled (e.g. fundamentally different parsing levels) | Document is added to the Exceptions list and permanently excluded from auto-pipeline processing |

After an analyst resolves a `changes-detected` document via any of the three actions, the document is no longer blocked and will be processed normally in subsequent cycles (unless added to Exceptions).

---

## CSV Output Format

> POC code: [`parse_xml.py`](parse_xml.py) (Canadian XML) · [`fetch_loda.py`](fetch_loda.py) (French law) · orchestrated via [`app.py`](app.py)

Each parsed document produces a CSV with the following columns:

| Column | Description |
|---|---|
| `Level 1 Header` | Top-level structural heading (e.g. Part, Title, Book) |
| `Level 2 Header` | Sub-heading (e.g. Chapter, Section group) |
| `Level 3 Header` | Article-level label (e.g. "Article 12") |
| `Section` | Normalized section identifier, prefixed `s.` (e.g. `s.14`, `s.Annexe I`) |
| `Notes` | Full plain-text content of the clause |

**Long clauses** are split into multiple rows at word boundaries (max 50,000 characters per chunk). Continuation rows have `Notes` prefixed with `[continued]`.

**Annexes / Schedules** — because they are often rendered as tables or images on the government website, the `Notes` field contains a reference link instead of raw text: `[To consult this schedule, please visit: {url}]`.

**Tables within articles** — a similar inline reference is prepended before the table HTML is stripped: `[To consult the table, please visit: {url}]`.

---

## Comparison Logic

> POC code: [`compare_csvs.py`](compare_csvs.py)

Comparison is performed using `Section` (section number) and `Notes` (clause text) as keys.

```
For each section in the new document:
│
├── Section number exists in old document?
│   ├── YES → Compare Notes (text)
│   │          ├── Same text    → Mark SAME    (carry Leborg section ID)
│   │          └── Different text → Mark UPDATED (carry Leborg section ID)
│   └── NO  → Mark NEW (no Leborg section ID assigned yet)
│
Sections present in old but absent in new → DELETED (excluded from output CSV)
```

- **Same** and **Updated** clauses carry the Leborg section ID from the existing record.
- **New** clauses are uploaded without a Leborg section ID.
- **Deleted** clauses do not appear in the output CSV.

> AI is **not** used in this standard comparison path. AI is used only within the [Pre-Parsed Documents logic](#pre-parsed-documents-logic) to filter false-positive changes before flagging a document for analyst review.

---

## Data Quality Checks

> POC code: [`app.py`](app.py) (irregularity checks run after each parse, lines 174–241)

After each CSV is generated, the pipeline runs automated checks and flags any issues for human review. The following irregularities are detected:

| Check | Description |
|---|---|
| No header | Row has no Level 1, 2, or 3 Header |
| No section number | Row has an empty `Section` field |
| No text | Row has an empty `Notes` field |
| Duplicate section numbers | Two or more non-`[continued]` rows share the same `Section` value |
| Header hierarchy violation | A child header is populated while its parent is blank (e.g. Level 2 filled, Level 1 empty) |
| Numeric section gaps | Integer section numbers are non-consecutive (e.g. s.12 followed by s.14) |
| HTML remnants | `Notes` field contains un-stripped HTML tags |
| Orphaned `[continued]` rows | A `[continued]` row has no preceding row with the same `Section` value |

Documents with any flagged issue are marked **Failed** in the dashboard and queued for manual review.

---

## Dashboard & UI

The dashboard ([UI mockup](https://nimonik-product-mockups.s3.us-east-1.amazonaws.com/Yurii_folder/leborg_parser_ui.html)) provides a single-page view of the pipeline state.

### Dashboard tab

- **KPI strip** — at-a-glance counts: Supported Jurisdictions, Total Parsed Documents, Updated This Month, Failed (needs review), Pre-parsed (needs review).
- **Active Parsers table** — lists each enabled parser with its module name, source domain, update-check method, document count, and last-run time.
- **Parsed Documents table** — full document list with status pills (Current / New / Updated / Failed / Review), jurisdiction, parser, Leborg reference ID, last-modified date, last-checked date, and a direct CSV download link (S3). Supports filtering by status and jurisdiction, free-text search, sortable columns, and pagination.
- **Exceptions table** — separate read-only list of documents permanently excluded from auto-pipeline processing (status `exceptions`), showing document title, jurisdiction, Leborg reference ID, and the date the exception was added.

### Pre-Parsed Review tab

Lists every document with status **Review** (`changes-detected`). For each:
1. Displays a summary of the detected changes (sections modified, added, or removed, with the source update date).
2. Provides a link to download the newly generated CSV for inspection.
3. Analyst chooses one of three actions:
   - **Approve as-is** — uploads the new CSV to Leborg; document transitions to standard auto-pipeline.
   - **Mark as manually uploaded** — analyst has corrected and uploaded the CSV in Leborg directly; tool marks the document as resolved without uploading.
   - **Add to exceptions** — permanently excludes the document from auto-pipeline processing.

### Fix Failed tab

Lists every document with status **Failed**. For each:
1. Displays the error message from the quality check.
2. Provides a drag-and-drop / file-browse zone to upload a corrected CSV.
3. On upload, the pipeline validates the CSV and syncs it to Leborg.
4. The document is marked **Updated** (if previously parsed) or **New** (first successful parse).

---

## Adding Jurisdictions

To activate a new jurisdiction, a responsible person must define and validate:

1. **ID/URL pattern** — how to identify qualifying documents for this source (e.g. URL prefix, XML endpoint template).
2. **Modification date logic** — how to extract the last-modified date from the government source.

Once validated, the configuration is pushed to the tool. Future plan: allow the responsible person to push directly without involving the engineering team.

---

## Leborg APIs

| API | Purpose | Reference |
|---|---|---|
| Leborg List Documents | Retrieve principal documents to process | [ready: API docs](https://github.com/Nimonik/leborg/wiki/Leborg-API-V2#list-documents) |
| Leborg List Legislation Sections | Fetch existing parsed sections for comparison | [ready: API docs](https://github.com/Nimonik/leborg/wiki/Leborg-API-V2#list-legislation-sections) |
| Leborg Check Parsed Text | Check whether a document already has parsed text in Leborg (used when no modification date is available) | [ready: API docs]([https://github.com/Nimonik/leborg/wiki/Leborg-API-V2#list-legislation-sections](https://github.com/Nimonik/leborg/wiki/Leborg-API-V2#get-a-legislations-in-use-legislation-text)) |
| Leborg Upload Version | Push new or updated parsed CSV to Leborg [ready: API docs]([https://github.com/Nimonik/leborg/wiki/Leborg-API-V2#list-legislation-sections](https://github.com/Nimonik/leborg/wiki/Leborg-API-V2#import-custom-legislation-sections-from-csv)) |

## External Government Sources

| Source | Purpose | Reference |
|---|---|---|
| Legifrance (PISTE) | Fetch French legislation content and metadata | api.piste.gouv.fr |
| Canada laws-lois XML | Fetch Canadian federal legislation as XML | laws-lois.justice.gc.ca |
