# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-page, no-build static web app: a Danish higher-education admission explorer that shows KOT (Den Koordinerede Tilmelding) cut-off GPAs for 2022–2026 and checks which programs a given GPA qualifies for.

- `index.html`: the whole app (markup, inline JS, a little inline CSS). Leaflet 1.9.4 still loads from the unpkg CDN, and map tiles come from Esri, so the map needs internet access.
- `data.js`: the dataset (~600 KB), a JSON object assigned to `window.KOT_DATA`. Shape: `{ title, source, totalPrograms, programs: [...] }`, 1,059 programs. It is a script rather than `data.json` so the page works when opened directly from disk: browsers block `fetch()` on `file://`, but allow `<script src>`. If you regenerate the data as JSON, wrap it as `window.KOT_DATA = <json>;`.
- `tailwind.css`: prebuilt, minified Tailwind **v3** stylesheet, committed. It contains only the classes used in `index.html`.

There is no package manager, linter or test suite.

## Running

Open `index.html` in a browser, or serve the folder (`python3 -m http.server 8000`). If `data.js` is missing or empty, the table shows an error instead of falling back to any built-in data.

## Rebuilding the CSS

After adding or changing Tailwind classes in `index.html` (including those in JS template strings), regenerate the stylesheet, or the new classes won't be styled:

```sh
npx tailwindcss@3 --content ./index.html -o tailwind.css --minify
```

Stay on v3: the page was designed against the v3 Play CDN, and v4 changes defaults such as border colour and ring width. Class names must appear as complete literals in `index.html`. Classes built by string concatenation won't be picked up.

## Data model (`programs[]` entries)

`optOmrNr` (KOT ID, string), `institution`, `programDetails` (one string: `"<name>, <location>, Studiestart: <start>"`), `city`, `lat`/`lng`, `ugLink`, `kotLink`, `gpaHistory` (`{"2022".."2026": number}`), `medianGpa`.

- Special values (constants `ALL_ADMITTED` / `ADMISSION_TEST` in `index.html`):
  - `0` = "Alle optaget" (everyone qualified admitted, no cut-off). Always counted as eligible. About 3,500 year entries.
  - `-1` = admission by entrance test or other criteria (e.g. Journalistik, Arkitekt). Shown as "Admission test" / "Test required", never greyed out and not counted as eligible. 102 year entries across 28 programs.
- `medianGpa` is stored in the JSON but **recomputed** on load from the positive `gpaHistory` values. A program with no positive value gets `-1` if any year is `-1`, otherwise `0`.
- Use `requiredGpa(p, yearVal)` to get the cut-off for the selected year or the median.

## How the inline JS fits together

- Global state: `kotData` (all rows), `filteredData` (after search/institution filter, then sorted), `currentPage`, `pageSize`, `sortCol` (`null` = data file order), `sortAsc`.
- `applyFilters()` rebuilds `filteredData` from the search box and institution dropdown, shows or hides the "Clear Filters" button, calls `applySort()`, then calls `renderPage()`. `renderPage()` reads the year/metric selector and the user's GPA, counts eligible rows across all of `filteredData`, and renders only the current page. GPA changes call `renderPage()` directly. Year changes call `applySort()` first, because GPA-column values depend on the year.
- Sorting: header cells carry `data-sort="<column>"`. Clicking a new column sorts it ascending; clicking the active column flips the direction; and the column header shows ↑/↓. Text and IDs compare with the shared `collator` (`Intl.Collator('da', {numeric: true})`), and ties break on KOT ID. Danish collation puts æ/ø/å after z and treats a leading "Aa" as "Å", so Aalborg and Aarhus sort last.
- The institution dropdown is built from the data by `populateInstitutionFilter()`, which lists every institution with its program count. Matching is exact (`p.institution === value`).
- The map markers (`mapHubs`, 6 hardcoded coordinates) are still hardcoded. Each `name` must exactly equal an `institution` value in the data, or "Filter Table" logs a warning and does nothing. The per-row `lat`/`lng`, `ugLink` and `kotLink` fields are currently unused: row links are hardcoded to the generic UG.dk and KOT pages.
- Rows are rendered with `innerHTML` string templates. Map popups call the global `window.filterByInst`.
