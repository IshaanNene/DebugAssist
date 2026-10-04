"""Hidden test for BUG-004 (never committed to the target repo). Copied to dispatch/tests/ at eval time."""

from datetime import UTC, datetime

from dispatch.db import Driver, Ride
from dispatch.matching import eta_seconds


def _ride() -> Ride:
    return Ride(
        pickup_lat=37.7955,
        pickup_lng=-122.3937,
        dropoff_lat=37.62,
        dropoff_lng=-122.38,
        assigned_at=datetime.now(UTC),
        status="driver_assigned",
    )


def test_driver_without_gps_fix_gets_an_estimate() -> None:
    driver = Driver(lat=None, lng=None, location_updated_at=datetime.now(UTC))
    eta = eta_seconds(driver, _ride())
    assert isinstance(eta, int) and eta > 0


def test_driver_never_located_gets_an_estimate() -> None:
    assert eta_seconds(Driver(lat=None, lng=None), _ride()) > 0
