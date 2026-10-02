import httpx
import pytest
import respx

from routing.exceptions import NoRouteError, RoutingUnavailableError
from routing.providers.osrm import OsrmProvider
from routing.types import Coordinate

BASE_URL = "https://osrm.test"
DALLAS = Coordinate(lat=32.7767, lng=-96.797)
DENVER = Coordinate(lat=39.7392, lng=-104.9903)
ROUTE_PATH = "/route/v1/driving/-96.797,32.7767;-104.9903,39.7392"

OK_PAYLOAD = {
    "code": "Ok",
    "routes": [
        {
            "distance": 1283_000.0,
            "duration": 43_260.0,
            "geometry": {
                "type": "LineString",
                "coordinates": [[-96.797, 32.7767], [-100.0, 36.0], [-104.9903, 39.7392]],
            },
        }
    ],
}


MIRROR_URL = "https://mirror.test/routed-car"


@pytest.fixture
def provider():
    return OsrmProvider(base_urls=[BASE_URL], timeout_seconds=1, user_agent="test-agent")


@pytest.fixture
def mirrored_provider():
    return OsrmProvider(
        base_urls=[BASE_URL, MIRROR_URL], timeout_seconds=1, user_agent="test-agent"
    )


@respx.mock
def test_route_requests_lng_lat_order_and_parses_the_response(provider):
    call = respx.get(f"{BASE_URL}{ROUTE_PATH}")
    call.mock(return_value=httpx.Response(200, json=OK_PAYLOAD))

    route = provider.route(DALLAS, DENVER)

    request = call.calls.last.request
    assert request.url.params["geometries"] == "geojson"
    assert request.url.params["overview"] == "full"
    assert request.headers["User-Agent"] == "test-agent"
    assert route.provider == "osrm"
    assert route.distance_miles == pytest.approx(797.2, abs=0.1)
    assert route.duration_minutes == 721
    assert route.geometry == ((-96.797, 32.7767), (-100.0, 36.0), (-104.9903, 39.7392))


@respx.mock
def test_no_route_code_becomes_no_route_error(provider):
    respx.get(f"{BASE_URL}{ROUTE_PATH}").mock(
        return_value=httpx.Response(400, json={"code": "NoRoute", "message": "Impossible route."})
    )

    with pytest.raises(NoRouteError) as excinfo:
        provider.route(DALLAS, DENVER)

    assert excinfo.value.details == {"provider_code": "NoRoute"}


@respx.mock
def test_server_error_becomes_routing_unavailable(provider):
    respx.get(f"{BASE_URL}{ROUTE_PATH}").mock(return_value=httpx.Response(502))

    with pytest.raises(RoutingUnavailableError):
        provider.route(DALLAS, DENVER)


@respx.mock
def test_timeout_is_retried_once_then_succeeds(provider):
    call = respx.get(f"{BASE_URL}{ROUTE_PATH}").mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json=OK_PAYLOAD)]
    )

    route = provider.route(DALLAS, DENVER)

    assert call.call_count == 2
    assert route.duration_minutes == 721


@respx.mock
def test_repeated_timeouts_become_routing_unavailable(provider):
    respx.get(f"{BASE_URL}{ROUTE_PATH}").mock(side_effect=httpx.ConnectTimeout("down"))

    with pytest.raises(RoutingUnavailableError):
        provider.route(DALLAS, DENVER)


@respx.mock
def test_timeout_on_the_first_host_fails_over_to_the_mirror(mirrored_provider):
    primary = respx.get(f"{BASE_URL}{ROUTE_PATH}").mock(side_effect=httpx.ConnectTimeout("down"))
    mirror = respx.get(f"{MIRROR_URL}{ROUTE_PATH}").mock(
        return_value=httpx.Response(200, json=OK_PAYLOAD)
    )

    route = mirrored_provider.route(DALLAS, DENVER)

    assert primary.call_count == 1
    assert mirror.call_count == 1
    assert route.duration_minutes == 721


@respx.mock
def test_server_error_on_the_first_host_fails_over_to_the_mirror(mirrored_provider):
    respx.get(f"{BASE_URL}{ROUTE_PATH}").mock(return_value=httpx.Response(503))
    respx.get(f"{MIRROR_URL}{ROUTE_PATH}").mock(return_value=httpx.Response(200, json=OK_PAYLOAD))

    assert mirrored_provider.route(DALLAS, DENVER).distance_miles == pytest.approx(797.2, abs=0.1)


@respx.mock
def test_both_hosts_down_is_routing_unavailable(mirrored_provider):
    respx.get(f"{BASE_URL}{ROUTE_PATH}").mock(side_effect=httpx.ConnectTimeout("down"))
    respx.get(f"{MIRROR_URL}{ROUTE_PATH}").mock(return_value=httpx.Response(502))

    with pytest.raises(RoutingUnavailableError):
        mirrored_provider.route(DALLAS, DENVER)
