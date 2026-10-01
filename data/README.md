# Data files

All geocoding happens offline against the files in this directory, so a clean clone needs no
geocoding API or key. Both place sources are works of the US federal government
(17 U.S.C. § 105) and carry no attribution or share-alike obligation.

| File | What it is | Source |
|---|---|---|
| `fuel-prices-for-be-assessment.csv` | OPIS truck-stop retail diesel prices supplied with the assessment (8,151 rows, no coordinates) | assessment attachment |
| `2026_Gaz_place_national.txt` | US Census Bureau Gazetteer, Places, 2026 vintage — every incorporated place and census-designated place with its internal-point coordinates (32,363 rows, unmodified) | [census.gov Gazetteer files](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html) |
| `gnis_populated_places.csv.gz` | USGS Geographic Names Information System, "Populated Place" features, trimmed to the columns the importer needs (174,097 rows; historical features dropped) | [USGS GNIS downloads](https://www.usgs.gov/us-board-on-geographic-names/download-gnis-data) |
| `city_aliases.csv` | Hand-maintained spellings that neither federal file resolves, with a note explaining each row | this repository |

## Provenance

Downloaded 2026-10-02.

| Archive | URL | SHA-256 |
|---|---|---|
| `2026_Gaz_place_national.zip` (1,214,650 bytes) | `https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2026_Gazetteer/2026_Gaz_place_national.zip` | `af678e2d990827c89ee39b98c82de6e90b693c7361ff0e559ae3076670dd2863` |
| `PopulatedPlaces_National_Text.zip` (6,192,581 bytes) | `https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/Topical/PopulatedPlaces_National_Text.zip` | `919fac887628b8547ec1b24fae319522a9481a56909c3914d1e0a2b56783147c` |

The Gazetteer text file is the archive's content as published. The GNIS extract is produced from
the archive's `Text/PopulatedPlaces_National.txt` by:

```sh
python scripts/build_gnis_extract.py data/raw/PopulatedPlaces_National.txt data/gnis_populated_places.csv.gz
```

USGS refreshes the GNIS archive at the same URL every other month, so re-running the script
against a newer download will produce a newer extract.

## Why two sources

The Gazetteer covers legal and statistical places, which is enough for user input and for most
truck-stop towns, but not for New England towns (county subdivisions, not places) nor for
unincorporated highway communities such as Sterling, ND or Dumont, CO. GNIS populated places
fill that gap. Against this price file the Gazetteer alone resolves about 93% of the 3,808 distinct
city/state pairs; Gazetteer plus GNIS resolves over 99%, and the remainder is listed in
`city_aliases.csv`.

Coordinates are NAD83 in both files; the difference from WGS84 is under two metres in the
contiguous US, so they are stored as EPSG:4326 without transformation.
