import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "workers_ai"


@pytest.fixture
def clef_fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "clef_basic.json").read_text())


@pytest.fixture
def basic_questions() -> dict[str, Any]:
    # Exactly the questions used to record the live fixtures on 2026-10-04.
    return {
        "needs_code_change": {
            "type": "noul",
            "instructions": "Does fixing this require a code change in our app?",
        },
        "category": {
            "type": "choice",
            "instructions": "Most likely category of the root cause.",
            "criteria": {
                "own_code": "bug in our code",
                "third_party": "third-party library",
                "infra": "infrastructure",
                "network": "network",
            },
        },
        "severity": {
            "type": "score",
            "instructions": "User impact severity.",
            "criteria": ["cosmetic", "minor", "major", "crash"],
        },
    }
