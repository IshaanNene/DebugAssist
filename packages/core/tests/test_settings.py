import pytest

from debugassist.core.settings import Integration, Mode, Settings


def make(**kwargs: object) -> Settings:
    # _env_file=None keeps the developer's real .env out of unit tests.
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPEN_ROUTER_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_KEY", "JIRA_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for i in Integration:
        monkeypatch.delenv(f"DA_MODE_{i.name}", raising=False)


def test_everything_is_mock_without_keys() -> None:
    assert set(make().modes().values()) == {Mode.MOCK}


def test_credentials_switch_integration_to_live() -> None:
    s = make(open_router_api_key="k", cloudflare_account_id="a", cloudflare_api_key="t")
    assert s.mode(Integration.LLM) is Mode.LIVE
    assert s.mode(Integration.CLEF) is Mode.LIVE
    assert s.mode(Integration.GITHUB) is Mode.MOCK


def test_jira_needs_url_and_email_too() -> None:
    assert make(jira_api_key="k").mode(Integration.JIRA) is Mode.MOCK
    s = make(jira_api_key="k", jira_base_url="https://x.atlassian.net", jira_email="a@b.c")
    assert s.mode(Integration.JIRA) is Mode.LIVE


def test_explicit_mock_overrides_credentials() -> None:
    assert make(open_router_api_key="k", da_mode_llm="mock").mode(Integration.LLM) is Mode.MOCK


def test_explicit_live_without_credentials_fails_loudly() -> None:
    with pytest.raises(ValueError, match="credentials are missing"):
        make(da_mode_clef="live").mode(Integration.CLEF)


def test_replay_only_for_llm() -> None:
    assert make(da_mode_llm="replay").mode(Integration.LLM) is Mode.REPLAY
    with pytest.raises(ValueError, match="replay"):
        make(da_mode_clef="replay").mode(Integration.CLEF)
