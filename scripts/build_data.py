# /// script
# requires-python = ">=3.10"
# dependencies = ["openpyxl"]
# ///
"""Build data.js from the official KOT "hovedtal" spreadsheets.

Usage (from the repo root, with the spreadsheets next to index.html):

    uv run scripts/build_data.py            # reads ./*.xlsx, writes ./data.js
    uv run scripts/build_data.py --src DIR --out FILE

Each spreadsheet's year is taken from the first 20xx in its filename. Programs are keyed
by OptOmrNr. Names and institutions come from the latest year a program is listed in.
Unknown kvote 1 values abort the build, so new KOT wording is caught instead of
silently mis-coded.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import openpyxl

SHEET = "hovedtal med filter"
# Columns in SHEET (0-based): OptOmrNr, Uddannelsessted, Optagelsesområde, ..., kvote 1 kvotient
COL_ID, COL_INST, COL_NAME, COL_K1 = 1, 2, 3, 8

# Per-year status codes written to data.js (index.html has matching labels).
CUTOFF = "cutoff"              # numeric kvote 1 cut-off
ALL_ADMITTED = "all_admitted"  # "Alle optaget": every qualified applicant admitted
QUOTA2_ONLY = "quota2_only"    # "Kun kvote 2" / "100 % kvote 2": no GPA quota
OUTSIDE_QUOTA = "outside_quota"  # "Uden for kvotesystem(et)": admitted outside KOT quotas
NOT_OFFERED = "not_offered"    # "Ikke oprettet": not offered that year
NONE_ADMITTED = "none_admitted"  # "Ingen optaget"
NOT_LISTED = "not_listed"      # program absent from that year's spreadsheet

# kvote 1 text (lower-cased, "ledige pladser" suffix removed) -> status
STATUS_TEXT = [
    (re.compile(r"^alle optaget$"), ALL_ADMITTED),
    (re.compile(r"^(kun kvote 2|100 ?% kvote 2)$"), QUOTA2_ONLY),
    (re.compile(r"^uden ?for kvotesystem(et)?$"), OUTSIDE_QUOTA),
    (re.compile(r"^ikke oprettet$"), NOT_OFFERED),
    (re.compile(r"^ingen optaget$"), NONE_ADMITTED),
]
VACANT_SUFFIX = re.compile(r",\s*ledige pladser\s*$", re.IGNORECASE)
NUMBER = re.compile(r"^-?\d+([.,]\d+)?$")

# Approximate centre of each location used in program names (town or postal district).
# None = no physical location (online programs).
LOCATIONS: dict[str, tuple[float, float] | None] = {
    "Aabenraa": (55.0443, 9.4174),
    "Aalborg": (57.0488, 9.9217),
    "Aalborg SV": (57.0300, 9.9000),
    "Aalborg SØ": (57.0280, 9.9600),
    "Aalborg Øst": (57.0150, 9.9850),
    "Aarhus C": (56.1567, 10.2108),
    "Aarhus N": (56.1800, 10.1900),
    "Auning": (56.4310, 10.3830),
    "Ballerup": (55.7316, 12.3633),
    "E-læring": None,
    "Esbjerg": (55.4765, 8.4594),
    "Esbjerg Ø": (55.4870, 8.4800),
    "Fredensborg": (55.9750, 12.4050),
    "Fredericia": (55.5657, 9.7526),
    "Frederiksberg": (55.6786, 12.5320),
    "Frederiksberg C": (55.6790, 12.5410),
    "Frederikshavn": (57.4407, 10.5366),
    "Grenaa": (56.4158, 10.8783),
    "Haderslev": (55.2530, 9.4890),
    "Herning": (56.1393, 8.9738),
    "Hillerød": (55.9267, 12.3109),
    "Hjørring": (57.4642, 9.9823),
    "Hobro": (56.6430, 9.7900),
    "Holbæk": (55.7175, 11.7128),
    "Holstebro": (56.3601, 8.6161),
    "Horsens": (55.8607, 9.8503),
    "Højbjerg": (56.1150, 10.2080),
    "Ikast": (56.1388, 9.1577),
    "Jelling": (55.7560, 9.4190),
    "Kalundborg": (55.6814, 11.0885),
    "Kgs. Lyngby": (55.7704, 12.5038),
    "Kolding": (55.4904, 9.4722),
    "København K": (55.6790, 12.5800),
    "København N": (55.6960, 12.5500),
    "København NV": (55.7050, 12.5300),
    "København S": (55.6600, 12.5950),
    "København SV": (55.6500, 12.5450),
    "København V": (55.6680, 12.5450),
    "København Ø": (55.7050, 12.5770),
    "Køge": (55.4580, 12.1821),
    "Lemvig": (56.5486, 8.3102),
    "Nexø": (55.0600, 15.1300),
    "Nykøbing F": (54.7691, 11.8743),
    "Næstved": (55.2299, 11.7609),
    "Odense C": (55.3959, 10.3883),
    "Odense M": (55.3690, 10.4280),
    "Randers C": (56.4607, 10.0364),
    "Randers SØ": (56.4500, 10.0700),
    "Roskilde": (55.6415, 12.0803),
    "Rønne": (55.1009, 14.7066),
    "Silkeborg": (56.1697, 9.5451),
    "Sisimiut": (66.9395, -53.6735),
    "Skive": (56.5667, 9.0279),
    "Skjern": (55.9500, 8.5000),
    "Slagelse": (55.4028, 11.3546),
    "Svendborg": (55.0598, 10.6068),
    "Sønderborg": (54.9138, 9.7922),
    "Thisted": (56.9552, 8.6946),
    "Tjele": (56.4900, 9.5800),
    "Tønder": (54.9331, 8.8667),
    "Vejle": (55.7093, 9.5357),
    "Vester Skerninge": (55.0750, 10.4600),
    "Viborg": (56.4532, 9.4020),
    "Viby J": (56.1290, 10.1640),
    "Vordingborg": (55.0080, 11.9110),
}


def parse_k1(value, where: str) -> dict:
    """Turn a raw 'kvote 1 kvotient' cell into {status, cutoff?, vacant?}."""
    if isinstance(value, (int, float)):
        return {"status": CUTOFF, "cutoff": round(float(value), 1)}
    text = str(value or "").strip()
    if NUMBER.match(text):
        return {"status": CUTOFF, "cutoff": round(float(text.replace(",", ".")), 1)}
    vacant = bool(VACANT_SUFFIX.search(text))
    core = VACANT_SUFFIX.sub("", text).strip().lower()
    for pattern, status in STATUS_TEXT:
        if pattern.match(core):
            entry = {"status": status}
            if vacant:
                entry["vacant"] = True
            return entry
    raise SystemExit(f"Unknown kvote 1 value {value!r} at {where}; add it to STATUS_TEXT")


def parse_location(name: str, oid: str) -> str:
    """'<program>, <location>, Studiestart: ...' -> '<location>' (program names may contain commas)."""
    parts = [p.strip() for p in name.split(",")]
    for i, part in enumerate(parts):
        if part.lower().startswith(("studiestart", "study start")) and i > 0:
            return parts[i - 1]
    raise SystemExit(f"Cannot find location in program name for {oid}: {name!r}")


def read_year(path: Path) -> dict[str, dict]:
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)[SHEET]
    rows = {}
    for rownum, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        row = list(row) + [None] * 10
        raw_id = row[COL_ID]
        if isinstance(raw_id, float) and raw_id.is_integer():
            raw_id = int(raw_id)
        if not (isinstance(raw_id, int) or (isinstance(raw_id, str) and raw_id.strip().isdigit())):
            continue  # institution header or blank row
        oid = str(int(raw_id))
        rows[oid] = {
            "institution": str(row[COL_INST] or "").strip(),
            "name": str(row[COL_NAME] or "").strip(),
            "k1": parse_k1(row[COL_K1], f"{path.name} row {rownum} ({oid})"),
        }
    return rows


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=root, help="folder with the KOT .xlsx files")
    ap.add_argument("--out", type=Path, default=root / "data.js")
    args = ap.parse_args()

    files = {}
    for path in sorted(args.src.glob("*.xlsx")):
        m = re.search(r"20\d\d", path.name)
        if not m:
            continue
        if m.group() in files:
            raise SystemExit(f"Two spreadsheets for {m.group()}: {files[m.group()].name}, {path.name}")
        files[m.group()] = path
    if not files:
        raise SystemExit(f"No KOT spreadsheets (*20xx*.xlsx) found in {args.src}")
    years = sorted(files)
    by_year = {y: read_year(files[y]) for y in years}

    all_ids = sorted({oid for rows in by_year.values() for oid in rows}, key=int)
    programs, unknown_locations = [], set()
    for oid in all_ids:
        listed = [y for y in years if oid in by_year[y]]
        latest = by_year[listed[-1]][oid]
        institution = latest["institution"] or next(
            (by_year[y][oid]["institution"] for y in reversed(listed) if by_year[y][oid]["institution"]), "")
        location = parse_location(latest["name"], oid)
        if location not in LOCATIONS:
            unknown_locations.add(location)
        coords = LOCATIONS.get(location)
        programs.append({
            "optOmrNr": oid,
            "institution": institution,
            "programDetails": latest["name"],
            "location": location,
            "lat": coords[0] if coords else None,
            "lng": coords[1] if coords else None,
            "years": {y: by_year[y][oid]["k1"] if oid in by_year[y] else {"status": NOT_LISTED} for y in years},
        })
    if unknown_locations:
        raise SystemExit(f"Add coordinates to LOCATIONS for: {sorted(unknown_locations)}")

    header = {
        "title": f"Danish higher education admission cut-offs (KOT {years[0]}–{years[-1]})",
        "source": "Den Koordinerede Tilmelding (KOT) hovedtal, Uddannelses- og Forskningsministeriet",
        "sourceFiles": {y: files[y].name for y in years},
        "years": years,
        "totalPrograms": len(programs),
    }
    # One program per line keeps diffs readable when the data is regenerated.
    lines = [json.dumps(p, ensure_ascii=False) for p in programs]
    head = json.dumps(header, ensure_ascii=False, indent=2)[:-2]  # drop closing "\n}"
    args.out.write_text(
        "// Generated by scripts/build_data.py from the KOT spreadsheets. Do not edit by hand.\n"
        f"window.KOT_DATA = {head},\n  \"programs\": [\n    " + ",\n    ".join(lines) + "\n  ]\n};\n",
        encoding="utf-8",
    )
    counts = {}
    for p in programs:
        for e in p["years"].values():
            counts[e["status"]] = counts.get(e["status"], 0) + 1
    print(f"Wrote {args.out} — {len(programs)} programs, years {', '.join(years)}", file=sys.stderr)
    print("Year-entry statuses: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())), file=sys.stderr)


if __name__ == "__main__":
    main()
