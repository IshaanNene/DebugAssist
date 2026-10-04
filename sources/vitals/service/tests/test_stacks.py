import json

from vitals_service.models import Frame
from vitals_service.stacks import SourceMap, enclosing_function, fingerprint, parse_stack, symbolicate

CHROME = """TypeError: Cannot read properties of undefined (reading 'riderId')
    at Kt (http://localhost:8080/assets/index-D4kq9Xa1.js:1:5)
    at async http://localhost:8080/assets/index-D4kq9Xa1.js:1:12
    at x (http://localhost:8080/node_modules/react.js:3:4)"""


def test_parse_v8_stack_innermost_last() -> None:
    frames = parse_stack(CHROME)
    assert [f.function for f in frames] == ["x", "<anonymous>", "Kt"]
    assert frames[-1].line == 1 and frames[-1].col == 5
    assert frames[0].in_app is False


def _encode(values: list[int]) -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    out = ""
    for v in values:
        v = (-v << 1) | 1 if v < 0 else v << 1
        while True:
            digit = v & 31
            v >>= 5
            out += chars[digit | (32 if v else 0)]
            if not v:
                break
    return out


SOURCE = """import { flag } from "../flags";

async function routeV2(link: string, navigate: Navigate) {
  const state = sessionStore.getState();
  const riderId = state.session!.riderId;
  navigate(link, { state: { riderId } });
}
"""


def make_map() -> str:
    # generated line 1: col 0 → src line 4 (0-based), col 2 → src line 0; col 11 → src line 2
    segs = [_encode([4, 0, 4, 18]), _encode([7, 0, -4, -16]), _encode([7, 0, 2, 0])]
    return json.dumps(
        {
            "version": 3,
            "sources": ["../../src/notifications/router.ts"],
            "sourcesContent": [SOURCE],
            "names": [],
            "mappings": ",".join(segs),
        }
    )


def test_sourcemap_lookup_and_symbolicate() -> None:
    sm = SourceMap.parse(make_map())
    assert sm.lookup(1, 5) == ("../../src/notifications/router.ts", 5, 19, None)
    frames, mapped = symbolicate(
        parse_stack(CHROME), lambda url: make_map() if url.endswith("D4kq9Xa1.js.map") else None
    )
    assert mapped
    top = frames[-1]
    assert (top.function, top.file, top.line) == ("routeV2", "src/notifications/router.ts", 5)


def test_enclosing_function_patterns() -> None:
    src = "class A {\n  private onVisibility = () => {\n    tick();\n  };\n  async fetchThing(x: number): Promise<void> {\n    go();\n  }\n}\nexport const useX = (a) => {\n  b();\n};\n"
    assert enclosing_function(src, 3) == "onVisibility"
    assert enclosing_function(src, 6) == "fetchThing"
    assert enclosing_function(src, 10) == "useX"


def test_fingerprint_ignores_line_numbers_and_asset_hashes() -> None:
    a = [Frame(function="routeV2", file="http://h/assets/index-AAAAAAAA.js", line=1, col=10)]
    b = [Frame(function="routeV2", file="http://h/assets/index-BBBBBBBB.js", line=1, col=99)]
    assert fingerprint("crash", "client", "TypeError", a, None, None) == fingerprint(
        "crash", "client", "TypeError", b, None, None
    )
    c = [Frame(function="other", file="x.js")]
    assert fingerprint("crash", "client", "TypeError", a, None, None) != fingerprint(
        "crash", "client", "TypeError", c, None, None
    )


def test_perf_fingerprint_uses_metric_and_culprit() -> None:
    f1 = fingerprint("perf", "client", None, [], "/ride/123", "cpu_busy_hidden")
    f2 = fingerprint("perf", "client", None, [], "/ride/456", "cpu_busy_hidden")
    assert f1 == f2


def test_enclosing_function_stops_at_top_level_block_end() -> None:
    src = "function crash() {\n  render();\n}\n\nvoid ready.then(() => {\n  route();\n});\n"
    assert enclosing_function(src, 2) == "crash"
    assert enclosing_function(src, 6) is None
