"""Trim the USGS GNIS PopulatedPlaces national file to the columns the importer needs.

Usage:
    python scripts/build_gnis_extract.py data/raw/PopulatedPlaces_National.txt \
        data/gnis_populated_places.csv.gz

Historical features are dropped. ``priority`` is 0 when the feature lends its name to its
USGS quadrangle map (the settlement itself) and 1 otherwise, which the resolver uses to break
ties between same-named places in one state.
"""

import csv
import gzip
import sys
from pathlib import Path

FIPS_TO_USPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE",
    "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA",
    "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM",
    "36": "NY", "37": "NC", "38": "ND", "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY", "72": "PR",
}  # fmt: skip


def main(source: Path, target: Path) -> None:
    kept = 0
    with (
        open(source, encoding="utf-8-sig", newline="") as infile,
        gzip.open(target, "wt", encoding="utf-8", newline="") as outfile,
    ):
        writer = csv.writer(outfile)
        writer.writerow(["feature_id", "state", "name", "lat", "lng", "priority"])
        for row in csv.DictReader(infile, delimiter="|"):
            state = FIPS_TO_USPS.get(row["state_numeric"])
            if state is None or "(historical)" in row["feature_name"]:
                continue
            priority = 0 if row["map_name"] == row["feature_name"] else 1
            writer.writerow(
                [
                    row["feature_id"],
                    state,
                    row["feature_name"],
                    row["prim_lat_dec"],
                    row["prim_long_dec"],
                    priority,
                ]
            )
            kept += 1
    print(f"wrote {kept} places to {target}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
