"""Hidden test for BUG-020 (never committed to the target repo). Copied to dispatch/tests/ at eval time."""

from datetime import UTC, datetime, timedelta

from dispatch.db import Driver, Ride
from dispatch.geo import Point, haversine_km, travel_seconds
from dispatch.matching import eta_seconds


def test_in_trip_eta_counts_down_to_the_dropoff() -> None:
    now = datetime.now(UTC)
    ride = Ride(
        pickup_lat=37.7955,
        pickup_lng=-122.3937,  # Ferry Building
        dropoff_lat=37.6213,
        dropoff_lng=-122.3790,  # SFO, ~19 km away
        assigned_at=now - timedelta(seconds=200),  # in the trip for ~80 s
        status="driver_assigned",
    )
    driver = Driver(lat=37.7955, lng=-122.3937)  # at the pickup
    trip = travel_seconds(haversine_km(Point(37.7955, -122.3937), Point(37.6213, -122.3790)))
    eta = eta_seconds(driver, ride, now)
    assert 600 < eta <= trip  # minutes to the drop-off, not "< 1 min" (distance to the pickup)
    later = eta_seconds(driver, ride, now + timedelta(seconds=60))
    assert later < eta or later == eta  # never goes up during the trip
