# Fuel Route API

Plans a driving route between two places in the USA and picks the cheapest places to refuel
along it. Given the vehicle's range and fuel economy it returns the route, the fuel stops, how
much to buy at each one and the total fuel cost.

- Django 6.1 · Django REST Framework · PostgreSQL 17 + PostGIS · Redis · Docker Compose
- One external call per request (routing); geocoding is fully offline
- Cost-optimal stops from a provably optimal greedy, not "cheapest station per 500 miles"

## Quick start

```sh
make up      # build the image, start PostGIS + Redis + the app, run migrations
make load    # load state boundaries, 206k US place centroids and 6,626 truck stops (offline, ~1 minute)
make test    # run the test suite
```

Then open http://localhost:8000/api/docs/ (Swagger UI) or import
[`postman/fuel-route-api.postman_collection.json`](postman/fuel-route-api.postman_collection.json).

Without `make` (Windows PowerShell or Git Bash), copy `.env.example` to `.env` once, then:

```sh
docker compose up -d --build
docker compose run --rm app sh -c "python manage.py migrate --noinput && python manage.py import_states && python manage.py import_places && python manage.py import_stations"
docker compose run --rm app pytest
```

## Step-by-step walkthrough for a first run

Everything runs in containers; the only prerequisite is Docker (Desktop or Engine with the
Compose plugin) and an internet connection for the routing engine and map tiles.

1. **Clone and start the stack** (about a minute the first time, building the image):
   ```sh
   git clone https://github.com/FahimJadid/fuel-route-api.git && cd fuel-route-api
   make up                     # Windows: copy .env.example to .env, then docker compose up -d --build
   ```
   `docker compose ps` should show `app` up and `db`/`redis` healthy.

2. **Load the data** (about a minute; migrations run first, nothing is downloaded):
   ```sh
   make load
   ```
   The last lines must read `stations: 6626`, `geocoded: 6626`, `unresolved: 0`.

3. **Check the service is healthy:**
   ```sh
   curl http://localhost:8000/api/v1/health/
   # {"status":"ok","checks":{"database":"ok","cache":"ok"}}
   ```

4. **Plan a trip:**
   ```sh
   curl -s -X POST http://localhost:8000/api/v1/trips/ \
     -H "Content-Type: application/json" \
     -d '{"origin": "Dallas, TX", "destination": "Denver, CO"}'
   ```
   Expect `201` with 2 stops, `"gallons": "77.938"`, `"cost": "211.07"` (full body below).
   The first call takes about a second — that is the single routing request. Repeat it: the
   route now comes from Redis and the whole request takes tens of milliseconds.

5. **See it on a map:** open the `links.map` URL from the response in a browser, e.g.
   `http://localhost:8000/api/v1/trips/<id>/map/`.

6. **Try the other input form and the vehicle parameters:**
   ```sh
   curl -s -X POST http://localhost:8000/api/v1/trips/ -H "Content-Type: application/json" \
     -d '{"origin": {"lat": 40.7128, "lng": -74.006}, "destination": "Los Angeles, CA", "max_range_miles": 400, "mpg": 7}'
   ```
   Expect `201`, about 2,805 miles and 17 stops.

7. **Provoke the error cases:**
   ```sh
   # misspelt place -> 400 place_not_found
   curl -s -X POST http://localhost:8000/api/v1/trips/ -H "Content-Type: application/json" \
     -d '{"origin": "Dalas, TX", "destination": "Denver, CO"}'
   # missing field + range below the minimum -> 400 validation_error with both fields in details
   curl -s -X POST http://localhost:8000/api/v1/trips/ -H "Content-Type: application/json" \
     -d '{"origin": "Dallas, TX", "max_range_miles": 10}'
   # 60-mile range -> 422 no_feasible_plan, details say where coverage breaks (mile 482.5)
   curl -s -X POST http://localhost:8000/api/v1/trips/ -H "Content-Type: application/json" \
     -d '{"origin": "Dallas, TX", "destination": "Denver, CO", "max_range_miles": 60}'
   # unknown id -> 404 not_found, same JSON envelope
   curl -s http://localhost:8000/api/v1/trips/00000000-0000-0000-0000-000000000000/
   ```

8. **Browse the API docs** at http://localhost:8000/api/docs/, or import the Postman
   collection — its requests mirror steps 3–7 and carry assertions.

9. **Run the tests** (real PostGIS, mocked routing HTTP; about ten seconds):
   ```sh
   make test
   ```

10. **Shut down:** `make down` keeps the database volume; `docker compose down -v` removes it.

## Example

```http
POST /api/v1/trips/
Content-Type: application/json

{"origin": "Dallas, TX", "destination": "Denver, CO"}
```

```json
{
  "id": "5153c3a0-471e-4028-a560-1e14c6d231c9",
  "origin": {"label": "Dallas, TX", "lat": 32.793333, "lng": -96.766513},
  "destination": {"label": "Denver, CO", "lat": 39.76185, "lng": -104.881105},
  "distance_miles": "779.4",
  "duration_minutes": 868,
  "vehicle": {"max_range_miles": "500.0", "mpg": "10.00", "tank_gallons": "50.00"},
  "route": {"type": "LineString", "coordinates": [[-96.766417, 32.793249], "... 335 points ..."]},
  "stops": [
    {
      "sequence": 1,
      "station": {"id": 2731, "opis_id": 66341, "name": "7-ELEVEN #218", "address": "I-44, EXIT 4",
                  "city": "Harrold", "state": "TX", "lat": 34.06757, "lng": -99.033091},
      "route_mile": 175.5,
      "detour_miles": 1.1,
      "price_per_gallon": "2.687",
      "gallons": 67.555,
      "cost": "181.52",
      "fuel_on_arrival_gallons": 0.0,
      "fuel_on_departure_gallons": 67.555,
      "action": "fill_up",
      "reason": "Fill the tank: nothing cheaper within range; next stop at mile 367."
    },
    {
      "sequence": 2,
      "station": {"id": 6406, "opis_id": 72816, "name": "QUIKTRIP #7914", "address": "I-27 EXIT 117",
                  "city": "Amarillo", "state": "TX", "lat": 35.199903, "lng": -101.830194},
      "route_mile": 367.2,
      "price_per_gallon": "2.846",
      "gallons": 10.383,
      "cost": "29.55",
      "fuel_on_arrival_gallons": 30.83,
      "fuel_on_departure_gallons": 41.213
    }
  ],
  "totals": {"gallons": "77.938", "cost": "211.07", "stops": 2},
  "starting_fuel": {"free_gallons": "0.000", "reserve_gallons": "17.550", "reserve_billed_at_stop": 1,
                    "reserve_cost": "47.16", "trip_gallons": "77.940"},
  "savings": {"baseline": "fill the tank at the farthest reachable station", "baseline_cost": "265.15",
              "baseline_stops": 1, "amount": "54.08", "percent": "20.4"},
  "fuel_ledger": {"carried_in": {"gallons": 0.0, "price_per_gallon": null, "value": "0.00"},
                  "purchased": {"gallons": 77.938, "cost": "211.07"},
                  "consumed": {"gallons": 77.938, "cost": "211.07"},
                  "carried_out": {"gallons": 0.0, "price_per_gallon": null, "value": "0.00"}},
  "assumptions": {"max_range_miles": "500.0", "mpg": "10.00", "tank_gallons": "50.00",
                  "initial_fuel_gallons": "0.000", "corridor_miles": "10.0", "minimum_purchase_gallons": 0,
                  "reserve_rule": "fuel needed to reach the first stop is billed at that stop",
                  "detour_cost_modelled": false, "routing_profile": "car"},
  "links": {"self": "http://localhost:8000/api/v1/trips/5153c3a0-.../",
            "map": "http://localhost:8000/api/v1/trips/5153c3a0-.../map/"},
  "created_at": "2026-10-02T05:15:22.118415Z"
}
```

`links.map` opens an HTML page with the route and the stops drawn on a map. `starting_fuel`
breaks down the reserve: the first stop's `gallons` already include the 17.55 gallons burned to
reach it, billed at that stop's price; `trip_gallons` equals `free_gallons` plus `totals.gallons`.

### Fuel ledger: chaining legs

Fuel in the tank is inventory. Each response carries a `fuel_ledger` that balances in gallons and
dollars — `carried_in + purchased = consumed + carried_out` — with the tank valued at its running
weighted-average cost, the way fleet accounting treats fuel on board. `totals.cost` stays "money
spent on this trip"; `fuel_ledger.consumed.cost` is what the trip actually burned.

To chain warehouse legs, ask the first leg to arrive with a reserve and hand what it carries
out to the next one:

```json
POST /api/v1/trips/  {"origin": "Dallas, TX", "destination": "Denver, CO", "end_fuel_gallons": 5}
→ "fuel_ledger": {"purchased": {"gallons": 82.938, "cost": "225.30"},
                  "consumed":  {"gallons": 77.938, "cost": "211.60"},
                  "carried_out": {"gallons": 5.0, "price_per_gallon": "2.740", "value": "13.70"}, ...}

POST /api/v1/trips/  {"origin": "Denver, CO", "destination": "Los Angeles, CA",
                      "initial_fuel_gallons": 5, "initial_fuel_price_per_gallon": "2.740"}
→ "fuel_ledger": {"carried_in": {"gallons": 5.0, "price_per_gallon": "2.740", "value": "13.70"},
                  "purchased": {"gallons": 98.713, "cost": "320.08"},
                  "consumed":  {"gallons": 103.713, "cost": "333.78"}, ...}
```

The 5 gallons carried out of Denver are valued at $2.740 — the running average of the two stops
on that leg, not the last pump's price — and are never bought again; their value is counted once,
in the second leg's consumption. Without a price, carried-in fuel is treated as free, as before.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/trips/` | Plan a trip. Body: `origin`, `destination` (each either `"City, ST"` or `{"lat", "lng"}`), optional `max_range_miles` (50–2000, default 500), `mpg` (1–50, default 10), `initial_fuel_gallons` (fuel already in the tank, default 0), `initial_fuel_price_per_gallon` (what that fuel cost on an earlier leg; omitted = unpriced) and `end_fuel_gallons` (fuel to arrive with, default 0). Both gallon figures are capped at the tank, `max_range_miles / mpg`. Returns `201`. |
| `GET` | `/api/v1/trips/{id}/` | Fetch a planned trip. |
| `GET` | `/api/v1/trips/{id}/map/` | The same trip rendered on a Leaflet map (HTML). |
| `GET` | `/api/v1/health/` | Database and cache health; `503` when either is down. |
| `GET` | `/api/docs/`, `/api/schema/` | Swagger UI and the OpenAPI schema. |

Every error has the same shape:

```json
{"error": {"code": "place_not_found", "message": "No place named 'Dalas' in TX.", "details": {"city": "Dalas", "state": "TX"}}}
```

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | a field is missing or out of range; `details` maps field → messages |
| 400 | `place_not_found`, `outside_usa` | the place name is unknown, or the coordinates fall outside the 48 contiguous states (checked against Census state boundaries) |
| 422 | `no_feasible_plan` | no station within range somewhere along the route; `details` has `from_mile` and the route |
| 422 | `no_route` | the routing engine found no drivable route |
| 503 | `routing_unavailable` | both routing deployments timed out or failed |
| 404 | `not_found` | unknown trip id |

## How it works

```
"Dallas, TX" ──► resolve (local Place table, ~1 ms)
                      │
                      ▼
            route (OSRM, cached in Redis 24 h) ──► simplify geometry (GEOS)
                      │
                      ▼
            corridor query (one PostGIS query, ~50 ms):
            stations within 10 mi of the route + each one's mile along the route
                      │
                      ▼
            fuel planner (pure Python, < 20 ms) ──► Trip row ──► JSON / map
```

### The fuel planner

The truck starts with just enough reserve to reach its first stop, which must lie within
`max_range_miles` of the origin. That reserve is billed at the first stop's price, as if the driver
had filled there before leaving. Optionally the caller declares fuel already in the tank with
`initial_fuel_gallons`; it is free, and only the shortfall to reach the first stop is billed. With
enough free fuel to cover the whole trip the plan has no stops and costs nothing. From any stop
the rule is the classic one for the gas-station problem on a fixed path (Khuller, Malekian &
Mestre, 2007):

- if a **cheaper** station is reachable on a full tank, buy **just enough** to get there;
- otherwise **fill the tank** and drive to the **cheapest** reachable station (ties go to the farther one).

That greedy is optimal for a fixed path. Every feasible first stop is evaluated and the cheapest
plan is kept. Purchased gallons plus free gallons always equal `distance / mpg`, so the total cost
is auditable; the response's `starting_fuel` block shows the reserve and what it cost. The
implementation is `trips/planner.py`; `tests/trips/test_planner.py` checks the edge cases and runs
200 seeded random instances against an independent exact shortest-path reference, asserting the
greedy never costs more.

### Data

The supplied price file has 8,151 rows: 620 Canadian stations, 678 station IDs repeated with
different prices, padded city names and one double-encoded name — and no coordinates. The import
(`stations/services/importer.py`) cleans the rows, drops Canada, merges duplicates into one
station with the **mean** price and a sample count, and geocodes each `City, State` against two
public-domain federal files committed in [`data/`](data/README.md): the Census Gazetteer (places)
and USGS GNIS (populated places). Twenty remaining spellings are resolved by an annotated alias
file. All 6,626 US stations end up with a coordinate; nothing is geocoded online, so a clean clone
needs no API key and the result is reproducible.

### Corridor search

Stations are matched to the route with one PostGIS query that transforms both into the CONUS
Albers projection (EPSG:5070, metres), filters with `ST_DWithin` on a functional GiST index, and
projects each station onto the line with `ST_LineLocatePoint` to get its mile along the route
(`stations/selectors.py`). A 2,800-mile route against 6,626 stations takes about 50 ms.

## Design decisions

| Topic | Choice | Why | Would reconsider if |
|---|---|---|---|
| Routing API | Public OSRM behind a `RoutingProvider` adapter, failing over between two independent deployments (project-osrm.org, FOSSGIS) | no key for reviewers, returns GeoJSON, ~200 ms; same engine and data on both hosts, so a failover changes availability, not answers | production traffic → self-hosted OSRM or OpenRouteService |
| Route geometry | fetch `overview=full`, simplify to 0.001° with GEOS | OSRM's own simplification gave 29 points for 795 miles — useless for a corridor; ours keeps ~1,700 points for a cross-country route | — |
| Geocoding | offline Census Gazetteer + GNIS, city-level | reproducible, public domain, no rate limits; public geocoders forbid or throttle bulk use | exit-level precision is needed → OSM `motorway_junction` exit refs |
| Corridor width | 10 miles | city centroids sit 1–3 miles from the interchange; truck stops are within ~2 miles of it | many false positives from parallel highways → narrower + exit-level data |
| Duplicate prices | mean + sample count | rows have no timestamp; mean is auditable | a date column appears → latest |
| Starting fuel | reserve billed at the first stop; optional free fuel via `initial_fuel_gallons` | by default the whole trip's fuel is priced en route, so costs are comparable across routes; a fleet that leaves the yard full passes the tank level | prices should reflect where the reserve was really bought → a `reserve_price` input |
| Stops storage | JSON snapshot on the trip | a stop's price is a point-in-time fact | cross-trip analytics on stations → normalise |
| Caching | Redis, keyed by provider + coordinates rounded to 4 dp, 24 h | the external call is the slow part; errors are never cached | — |

## Rules, industry mapping and next steps

Every response carries an `assumptions` block (range, mpg, tank, free fuel, corridor, reserve
rule, minimum purchase, routing profile), a `savings` block comparing the plan with the naive
"fill the tank at the farthest reachable station" policy run through the same engine, and an
`action`/`reason` pair on every stop (`fill_up`, `partial`, `final_leg`). That mirrors how fleet
fuel optimizers (Trimble Expert Fuel, ProMiles) and consumer planners (Tesla, Google Maps EV
routing, ABRP) work: one prescriptive plan with gallons per stop, the rules stated, and the
reasoning visible, rather than a menu of alternative plans. The per-stop row — mile, fuel on
arrival, gallons, price, cost, fuel on departure, detour — is the same shape as ProMiles'
`FuelOptimizationRow`; the "fill up, or buy just enough to reach cheaper fuel" rule is the one
ProMiles documents and the one Khuller, Malekian and Mestre proved optimal for a fixed route.

Detours are reported, not priced: `detour_miles` is each station's distance from the route, and
with a 10-mile corridor the worst case costs about 2 gallons of extra driving at 10 mpg. With
more time, in the order a fleet would ask for them:

- Per-stop override: tap a stop, see the nearest alternatives with the cost delta, replan.
- Price the detour into the choice and expose a `max_detour_miles` limit (fleets use ~2 miles).
- A per-stop time penalty or minimum purchase, which turns the greedy into a dynamic program
  over (station, fuel level) with a "fewer stops / cheapest" toggle.
- A minimum on-board level at every point of the trip (the destination reserve already exists
  as `end_fuel_gallons`).
- Ex-tax pricing and network discounts, which can change which stop wins.
- Station eligibility filters (chains, parking, amenities) and price timestamps.
- A reconciliation endpoint comparing planned with purchased gallons.

Deliberately not planned: alternative complete plans (no shipping product shows them),
re-routing to chase cheaper fuel or a second routing call, fuel-card enforcement, and live or
crowd-sourced prices.

## Assumptions and scope

- Stops are assumed to be on the route; detour distance to a station is not modelled.
- Routes use OSRM's car profile; truck-specific restrictions (weight, height, hazmat) are not
  applied. A route whose shortest path crosses Canada (Detroit → Buffalo) is accepted as the
  router returns it, but only US stations are known, so that stretch has no fuel coverage.
- Origin equal to destination is valid: 0 miles, no stops, `$0`.
- Prices are the supplied file's values; no live prices, fuel-card discounts or state fuel taxes.
- The reserve to reach the first stop is billed at that stop, so by default every trip has at
  least one stop. A route with no station within range (some corridors in California and the
  Pacific Northwest) returns `422` with the mile where coverage breaks. With enough
  `initial_fuel_gallons` to cover the whole distance a trip legitimately returns zero stops and
  `$0`.
- The planner may produce small top-ups when prices creep up along the route. That is cost-optimal
  but a real fleet would add a minimum purchase or a per-stop penalty, which turns the problem
  into a dynamic program.
- No authentication or rate limiting; the API is meant to sit behind a gateway.

## Performance

Measured on the included data (Docker on a laptop):

| Step | Time |
|---|---|
| resolve `"City, ST"` | 1–2 ms |
| OSRM call (uncached) | 200–1,200 ms |
| route from Redis | ~1 ms |
| corridor query, NYC→LA (1,752-point line) | ~55 ms |
| planner, NYC→LA (459 candidate stations) | ~19 ms |
| **whole request, warm** | **~20–60 ms** |

Every request logs a JSON line with `duration_ms` and returns the same figure in an
`X-Response-Time-Ms` header, so the server's own time can be read next to the client's.

## Project structure

```
config/      settings (base/local/test/prod), urls
core/        health endpoint, request logging, uniform error handler
geo/         Place model, Gazetteer/GNIS import, "City, ST" resolver
stations/    Station model, price-file import, corridor selector (PostGIS)
routing/     RoutingProvider interface, OSRM adapter, cached route service
trips/       fuel planner, Trip model, planning service, API, map page
data/        the price file and the place data, with provenance
tests/       pytest suite mirroring the apps
```

Views are thin; business logic lives in `services`/`selectors`/`planner`; external calls sit
behind adapters.

## Testing and tooling

```sh
make test     # pytest, ~290 tests, needs the compose stack
make lint     # ruff check + ruff format --check
make format
```

Tests use a real PostGIS database and a local-memory cache; the only thing stubbed is the routing
HTTP call (`respx`). Dependencies are locked with `uv` (`uv.lock`); `pre-commit` runs ruff.

## Configuration

All settings come from the environment; `.env.example` lists every variable with the values
used by the compose stack.

| Variable | Required | Compose value / default | Meaning |
|---|---|---|---|
| `SECRET_KEY` | yes | placeholder in `.env.example` | Django secret; change outside local development |
| `DATABASE_URL` | yes | `postgis://fuel:fuel@db:5432/fuel` | PostGIS connection |
| `REDIS_URL` | yes | `redis://redis:6379/1` | cache |
| `ALLOWED_HOSTS` | prod only | `localhost,127.0.0.1` | comma-separated hosts |
| `OSRM_BASE_URLS` | no | `https://router.project-osrm.org,https://routing.openstreetmap.de/routed-car` | routing engines, tried in order on timeouts or 5xx |
| `ROUTING_TIMEOUT_SECONDS` | no | `10` | per-request timeout |
| `ROUTE_CACHE_SECONDS` | no | `86400` | route cache TTL |
| `FUEL_CORRIDOR_MILES` | no | `10` | corridor half-width |
| `VEHICLE_MAX_RANGE_MILES`, `VEHICLE_MPG` | no | `500`, `10` | vehicle defaults, overridable per request |

## With more time

- Model detours: price each station's off-route distance into the plan.
- A per-stop penalty or minimum purchase, solved with a DP over (station, fuel level).
- Exit-level station positions from OpenStreetMap `motorway_junction` refs.
- Negative caching of `no_route` results; a self-hosted OSRM with an `avoid_countries` option.
- API keys and throttling; a multi-stage Docker build; GCP deployment (Cloud Run + Cloud SQL + Memorystore).
