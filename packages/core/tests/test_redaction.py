import pytest

from debugassist.core.redaction import redact, redact_text


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("mail me at jane.doe+ride@example.co.uk now", "mail me at [email] now"),
        ("call +1 415-555-0134 please", "call [phone] please"),
        ("card 4242 4242 4242 4242 exp 12/29", "card [card] exp 12/29"),
        ("Authorization: Bearer abcdefghijklmnop123", "Authorization: Bearer [token]"),
        ("token=sk-live_ABCDEFGHIJ1234567890", "token=[token]"),
        (
            "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            "jwt [token]",
        ),
        ("at 37.795512, -122.393711 near the ferry", "at 37.8, -122.39 near the ferry"),
    ],
)
def test_redacts(raw: str, expected: str) -> None:
    assert redact_text(raw) == expected


@pytest.mark.parametrize(
    "safe",
    [
        "ride r1 took 1234 ms",
        "version 1.4.0 build 20261004",
        "order 1234567890123 is not a card",  # fails Luhn
        "eta 300 seconds, 4.8 rating",
        "TypeError: Cannot read properties of undefined (reading 'riderId')",
    ],
)
def test_leaves_ordinary_text_alone(safe: str) -> None:
    assert redact_text(safe) == safe


def test_redacts_nested_structures_and_coordinates() -> None:
    data = {
        "pickup": {"name": "Ferry Building", "lat": 37.795512, "lng": -122.393711},
        "logs": ["user bob@example.com logged in", {"msg": "phone 4155550134"}],
        "count": 3,
        "ok": True,
    }
    out = redact(data)
    assert out["pickup"] == {"name": "Ferry Building", "lat": 37.8, "lng": -122.39}
    assert out["logs"] == ["user [email] logged in", {"msg": "phone [phone]"}]
    assert out["count"] == 3 and out["ok"] is True
