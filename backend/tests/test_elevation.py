"""Elevation effect compares pace on climbs with pace on the flat."""

from app.metrics.elevation import elevation_effect


def _course() -> list[dict]:
    samples = [{"distance_meters": 0.0, "elapsed_seconds": 0.0, "altitude_meters": 10.0, "speed_mps": 4.0}]
    distance = 0.0
    elapsed = 0.0
    segments = [
        (1609.344, 4.0, 10.0, 10.0),
        (1609.344, 3.4, 10.0, 50.0),
        (1609.344, 4.4, 50.0, 10.0),
    ]
    for length, speed, start_alt, end_alt in segments:
        steps = 40
        for step in range(1, steps + 1):
            fraction = step / steps
            samples.append(
                {
                    "distance_meters": distance + length * fraction,
                    "elapsed_seconds": elapsed + (length / speed) * fraction,
                    "altitude_meters": start_alt + (end_alt - start_alt) * fraction,
                    "speed_mps": speed,
                }
            )
        distance += length
        elapsed += length / speed
    return samples


def test_climb_is_slower_than_flat_and_names_the_mile() -> None:
    effect = elevation_effect(_course(), gain_meters=40, loss_meters=40)
    assert effect["available"] is True
    assert effect["climb_versus_flat_seconds_per_mile"] > 20
    assert effect["descent_versus_flat_seconds_per_mile"] < -10
    assert effect["steepest_climb"]["label"] == "Mile 2"
    assert effect["steepest_descent"]["label"] == "Mile 3"
    assert "Recorded elevation gain was 40 m" in effect["note"]
    assert "Uphill running was" in effect["note"]


def test_missing_altitude_has_no_elevation_effect() -> None:
    samples = [
        {"distance_meters": index * 10, "elapsed_seconds": index * 3, "speed_mps": 3.5}
        for index in range(80)
    ]
    effect = elevation_effect(samples, gain_meters=12, loss_meters=10)
    assert effect["available"] is False
    assert effect["note"] is None
