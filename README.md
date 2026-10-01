# Fuel Route API

Plans a driving route between two locations in the USA and picks the cheapest places to refuel along it,
given the vehicle's range and fuel economy.

## Quick start

```sh
make up        # builds the image, starts PostGIS + Redis + the app, runs migrations
```

The API is served at http://localhost:8000/ and the interactive docs at http://localhost:8000/api/docs/.
