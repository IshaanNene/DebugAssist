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


SECRETS = [  # every credential in .env.example, with realistic fake values (audit P3-14)
    ("GROQ_CLOUD_API={}", "gsk_0123456789abcdefABCDEFghij"),
    ("OPEN_ROUTER_API_KEY={}", "sk-or-v1-0123456789abcdef0123456789abcdef"),
    ("CLOUDFLARE_API_KEY={}", "Abc123def456Ghi789jkl012MNO345pqr678stu9"),
    ("GITHUB_TOKEN={}", "ghp_0123456789abcdefABCDEFghijklmnopqr"),
    ("JIRA_API_KEY={}", "ATATT3xFfGF0abcdefghijklmnopqrstuvwxyz0123"),
    ("DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890/{}", "AbCdEf-gh_IJklmnop"),
    ("GITHUB_APP_WEBHOOK_SECRET={}", "s3cr3t-value-123"),
    ("token {} in a message", "ghs_0123456789abcdefABCDEF"),
    ("git push https://x-access-token:{}@github.com/a/b.git", "ghs_0123456789abcdef"),
    ("posting to https://discord.com/api/webhooks/1234567890/{} failed", "AbCdEf-gh_IJklmnop"),
    ("a Jira token {} alone", "ATATT3xFfGF0abcdefghijklmnopqrstuvwxyz0123"),
]


@pytest.mark.parametrize("template,secret", SECRETS)
def test_redacts_every_credential_this_project_uses(template: str, secret: str) -> None:
    from debugassist.core.redaction import redact_secrets

    raw = template.format(secret)
    for out in (redact_text(raw), redact_secrets(raw)):
        assert secret not in out and "[token]" in out
