# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-page, no-build static web app: a Danish higher-education admission explorer that shows KOT (Den Koordinerede Tilmelding) cut-off GPAs for 2022–2026 and checks which programs a given GPA qualifies for.

- `index.html`: the whole app (markup, inline JS, a little inline CSS). Leaflet 1.9.4 still loads from the unpkg CDN, and map tiles come from Esri, so the map needs internet access.
- `data.js`: the dataset (~490 KB, 1,059 programs), **generated** by `scripts/build_data.py`; don't edit it by hand. It assigns a JSON object to `window.KOT_DATA`. It is a script rather than `data.json` so the page works when opened directly from disk: browsers block `fetch()` on `file://`, but allow `<script src>`.
- `scripts/build_data.py`: builds `data.js` from the official KOT "hovedtal" spreadsheets.
- `*.xlsx`: the KOT source spreadsheets, one per year. They are gitignored and kept only locally, so `data.js` can only be rebuilt on a machine that has them.
- `tailwind.css`: prebuilt, minified Tailwind **v3** stylesheet, committed. It contains only the classes used in `index.html`.

There is no package manager, linter or test suite.

## Rebuilding the data

With the spreadsheets in the repo root:

```sh
uv run scripts/build_data.py   # dependencies (openpyxl) are declared inline (PEP 723)
```

- The script takes each file's year from the first `20xx` in its filename and reads the `hovedtal med filter` sheet. Column positions are fixed in `COL_*`.
- It aborts on any kvote 1 text it doesn't recognise, or on a location missing from `LOCATIONS`. Add new wording to `STATUS_TEXT` (and a matching entry in `STATUS` in `index.html`), and new places to `LOCATIONS`.
- When adding a year, also add it to the year `<select>` in `index.html`, which is still hardcoded.

## Running

Open `index.html` in a browser, or serve the folder (`python3 -m http.server 8000`). If `data.js` is missing or empty, the table shows an error instead of falling back to any built-in data.

## Rebuilding the CSS

After adding or changing Tailwind classes in `index.html` (including those in JS template strings), regenerate the stylesheet, or the new classes won't be styled:

```sh
npx tailwindcss@3 --content ./index.html -o tailwind.css --minify
```

Stay on v3: the page was designed against the v3 Play CDN, and v4 changes defaults such as border colour and ring width. Class names must appear as complete literals in `index.html`. Classes built by string concatenation won't be picked up.

## Data model

Top level: `title`, `source`, `sourceFiles` (year → filename), `years`, `totalPrograms`, `programs`.

Each program has these fields:

- `optOmrNr`: the KOT ID, a string.
- `institution` and `programDetails`: both taken from the **latest** year the program is listed. `programDetails` is one string, `"<name>, <location>, Studiestart: <start>"`.
- `location`: parsed from `programDetails`.
- `lat`/`lng`: approximate town or postal-district centre from `LOCATIONS`, `null` for "E-læring" (online).
- `years`: `{ "<year>": {status, cutoff?, vacant?} }` for every year.

`status` is the KOT kvote 1 value. The table maps each status to its `STATUS` entry in `index.html`:

| status | KOT text | `kind` in `index.html` |
|---|---|---|
| `cutoff` (+ `cutoff` number) | numeric kvote 1 kvotient | compared with the user's GPA |
| `all_admitted` | Alle optaget | always eligible |
| `quota2_only` | Kun kvote 2 / 100 % kvote 2 | `other`: not decided by GPA, not counted as eligible |
| `outside_quota` | Uden for kvotesystem(et) | `other` |
| `not_offered` | Ikke oprettet | `unavailable`: greyed out |
| `none_admitted` | Ingen optaget | `unavailable` |
| `not_listed` | (program absent from that year's file) | `unavailable` |

`vacant: true` means the KOT text ended in ", ledige pladser" (seats left). It is shown under the label.

On load, `index.html` computes `p.median`. This is the median of the years with a numeric cut-off. A program with no cut-off in any year shows its status from the most recent year it was listed. Use `entryFor(p, yearVal)` for the selected year or the median, `classify(entry, userGpa)` for eligibility, and `gpaSortKey(entry)` for sorting. When sorting by GPA, entries without a GPA bar always go last, in either direction.

## How the inline JS fits together

- Global state: `kotData` (all rows), `filteredData` (after search/institution filter, then sorted), `currentPage`, `pageSize`, `sortCol` (`null` = data file order), `sortAsc`.
- `applyFilters()` rebuilds `filteredData` from the search box and institution dropdown, shows or hides the "Clear Filters" button, calls `applySort()`, then calls `renderPage()`. `renderPage()` reads the year/metric selector and the user's GPA, counts eligible rows across all of `filteredData`, and renders only the current page. GPA changes call `renderPage()` directly. Year changes call `applySort()` first, because GPA-column values depend on the year.
- Sorting: header cells carry `data-sort="<column>"`. Clicking a new column sorts it ascending; clicking the active column flips the direction; and the column header shows ↑/↓. Text and IDs compare with the shared `collator` (`Intl.Collator('da', {numeric: true})`), and ties break on KOT ID. Danish collation puts æ/ø/å after z and treats a leading "Aa" as "Å", so Aalborg and Aarhus sort last.
- The institution dropdown is built from the data by `populateInstitutionFilter()`, which lists every institution with its program count. Matching is exact (`p.institution === value`).
- The map markers (`mapHubs`, 6 hardcoded coordinates) are still hardcoded and don't use the per-program `lat`/`lng` yet. Each `name` must exactly equal an `institution` value in the data, or "Filter Table" logs a warning and does nothing. Row links are hardcoded to the generic UG.dk and KOT pages, because the spreadsheets have no per-program links.
- Rows are rendered with `innerHTML` string templates. Data values go through `esc()`. Map popups call the global `window.filterByInst`.
