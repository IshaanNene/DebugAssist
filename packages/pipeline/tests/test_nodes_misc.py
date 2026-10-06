def test_known_flag_strips_llm_commentary() -> None:
    from debugassist.pipeline.nodes import known_flag

    known = ["notif_router_v2", "surge_pricing"]
    assert known_flag("surge_pricing", known) == "surge_pricing"
    assert (
        known_flag("notif_router_v2 (irrelevant — flag is off for all affected sessions)", known)
        == "notif_router_v2"
    )
    assert known_flag("notif_router_v2_beta", known) is None
    assert known_flag("none", known) is None
