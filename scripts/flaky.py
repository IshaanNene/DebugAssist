"""Compare JUnit XML files from repeated runs of the same suite; fail naming every test whose outcome changed."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict


def outcomes(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for case in ET.parse(path).iter("testcase"):  # noqa: S314 - see above
        name = f"{case.get('classname')}::{case.get('name')}"
        kinds = {child.tag for child in case}
        out[name] = (
            "failed" if kinds & {"failure", "error"} else "skipped" if "skipped" in kinds else "passed"
        )
    return out


def main(paths: list[str]) -> int:
    seen: dict[str, set[str]] = defaultdict(set)
    for p in paths:
        for name, result in outcomes(p).items():
            seen[name].add(result)
    flaky = sorted(n for n, results in seen.items() if len(results) > 1)
    always_failing = sorted(n for n, results in seen.items() if results == {"failed"})
    for n in flaky:
        print(f"flaky: {n} ({', '.join(sorted(seen[n]))})")
    for n in always_failing:
        print(f"failing in every run: {n}")
    print(f"{len(seen)} tests, {len(paths)} runs: {len(flaky)} flaky, {len(always_failing)} always failing")
    return 1 if flaky or always_failing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
