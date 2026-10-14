"""What system an agent is told it works on. MiniRide issues keep their prompts byte for byte; a real repository
(a GitHub issue, `issue.about` set) gets its own one-line description instead, and loses the MiniRide-only rules."""

from __future__ import annotations

from debugassist.pipeline.state import Issue

MINIRIDE = "MiniRide (a ride-hailing\napp: React client, Node GraphQL gateway, Python dispatch, Go payments)"
OWNERSHIP = (
    "- miniride-client and miniride-services (gateway, dispatch, payments) are ours, apart from vendored code\n"
    "  (below): a defect there is own_code, even in another repo or service than the one that saw the symptom.\n"
)


def for_issue(prompt: str, issue: Issue | None) -> str:
    if issue is None or not issue.about:
        return prompt
    return prompt.replace(MINIRIDE, issue.about).replace(OWNERSHIP, "")
