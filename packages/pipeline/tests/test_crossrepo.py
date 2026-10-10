from pathlib import Path

import pytest

from debugassist.pipeline.crossrepo import plan_handoff
from debugassist.pipeline.state import Issue

SERVICES_CFG = """
repo: miniride-services
default_agent_type: backend-error
components:
  gateway: {path: gateway, language: typescript}
  dispatch: {path: dispatch, language: python}
  payments: {path: payments, language: go}
"""


def client_issue() -> Issue:
    return Issue(
        source="bugdrop",
        id="BD-1001",
        url="http://bugdrop/reports/BD-1001",
        title="See prices stays disabled",
        kind="bug_report",
        app="miniride-client",
        platform="web",
        version="1.7.3",
        first_version="1.7.3",
        last_version="1.7.3",
        repo="miniride-client",
        gh_repo="IshaanNene/miniride-client",
        component=".",
        language="typescript",
    )


@pytest.fixture
def services(tmp_path: Path) -> Path:
    (tmp_path / ".DebugAssist").mkdir()
    (tmp_path / ".DebugAssist" / "pipeline.yaml").write_text(SERVICES_CFG)
    (tmp_path / "gateway" / "src").mkdir(parents=True)
    (tmp_path / "gateway" / "src" / "backends.ts").write_text("export {}\n")
    return tmp_path


def test_hands_off_to_the_service_component(services: Path) -> None:
    plan = plan_handoff(client_issue(), "miniride-services", "gateway/src/backends.ts", services)
    assert plan == {
        "repo": "miniride-services",
        "gh_repo": "IshaanNene/miniride-services",
        "component": "gateway",
        "language": "typescript",
        "default_agent_type": "backend-error",
    }


def test_accepts_owner_prefixed_repo_names(services: Path) -> None:
    plan = plan_handoff(client_issue(), "IshaanNene/miniride-services", "./gateway/src/backends.ts", services)
    assert plan and plan["component"] == "gateway"


def test_never_hands_off_on_a_path_that_does_not_exist(services: Path) -> None:
    assert plan_handoff(client_issue(), "miniride-services", "gateway/src/schema.ts", services) is None


def test_stays_for_the_same_or_an_unknown_repo(services: Path) -> None:
    assert plan_handoff(client_issue(), "miniride-client", "src/screens/Search.tsx", services) is None
    assert plan_handoff(client_issue(), "some-other-repo", "gateway/src/backends.ts", services) is None
