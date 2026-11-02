# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-page, no-build static web app: a Danish higher-education admission explorer that shows KOT (Den Koordinerede Tilmelding) cut-off GPAs for 2022–2026 and checks which programs a given GPA qualifies for.

- `index.html`: the whole app (markup, inline JS, inline CSS). Tailwind (Play CDN) and Leaflet 1.9.4 load from CDNs, so the page needs internet access to render properly.
- `data.json`: the dataset (~600 KB). Shape: `{ title, source, totalPrograms, programs: [...] }`, 1,059 programs.

There is no package manager, build step, linter or test suite.

## Running

`fetch()` doesn't work over `file://`, so serve the directory over HTTP:

```sh
python3 -m http.server 8000   # then open http://localhost:8000/
```

`loadData()` fetches `data.json`. If that fails, the page shows an error in the table (with a hint when opened via `file://`) instead of falling back to any built-in data.

## Data model (`programs[]` entries)

`optOmrNr` (KOT ID, string), `institution`, `programDetails` (one string: `"<name>, <location>, Studiestart: <start>"`), `city`, `lat`/`lng`, `ugLink`, `kotLink`, `gpaHistory` (`{"2022".."2026": number}`), `medianGpa`.

- Special values (constants `ALL_ADMITTED` / `ADMISSION_TEST` in `index.html`):
  - `0` = "Alle optaget" (everyone qualified admitted, no cut-off). Always counted as eligible. About 3,500 year entries.
  - `-1` = admission by entrance test or other criteria (e.g. Journalistik, Arkitekt). Shown as "Admission test" / "Test required", never greyed out and not counted as eligible. 102 year entries across 28 programs.
- `medianGpa` is stored in the JSON but **recomputed** on load from the positive `gpaHistory` values. A program with no positive value gets `-1` if any year is `-1`, otherwise `0`.
- Use `requiredGpa(p, yearVal)` to get the cut-off for the selected year or the median.

## How the inline JS fits together

- Global state: `kotData` (all rows), `filteredData` (after search/institution filter), `currentPage`, `pageSize`, `sortDir`.
- `applyFilters()` rebuilds `filteredData` from the search box and institution dropdown, then calls `renderPage()`. `renderPage()` reads the year/metric selector and the user's GPA, counts eligible rows across all of `filteredData`, and renders only the current page. Year and GPA changes call `renderPage()` directly because they don't change the filtered set.
- `sortTable(col)` sorts `filteredData` in place, so the sort is lost on the next `applyFilters()`.
- Institution matching uses `p.institution.includes(value)`. That is why short dropdown labels such as "Copenhagen Business School" and "VIA University College" match the longer official names in the data ("Copenhagen Business School - Handelshøjskolen", "Professionshøjskolen VIA University College").
- The institution dropdown (10 options) and the map markers (`mapHubs`, 6 hardcoded coordinates) are hardcoded. They are not built from the data, which has 36 institutions. The per-row `lat`/`lng`, `ugLink` and `kotLink` fields are currently unused: row links are hardcoded to the generic UG.dk and KOT pages.
- Rows are rendered with `innerHTML` string templates. Map popups call the global `window.filterByInst`.
