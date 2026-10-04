"""Stack parsing, source-map symbolication and fingerprinting."""

from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache

from vitals_service.models import Frame

# V8 / Chrome:  "    at fn (http://host/assets/index-AbC123.js:1:2345)"  or  "    at http://host/x.js:1:2"
V8_FRAME = re.compile(
    r"^\s*at (?:async )?(?:(?P<fn>.+?) \()?(?P<file>(?:https?|file|node):[^\s)]+|/[^\s)]+):(?P<line>\d+):(?P<col>\d+)\)?$"
)
# Firefox / Safari: "fn@http://host/x.js:1:2"
GECKO_FRAME = re.compile(r"^(?P<fn>[^@]*)@(?P<file>.+?):(?P<line>\d+):(?P<col>\d+)$")


def parse_stack(stack: str) -> list[Frame]:
    """Parse a JS/Node stack into frames, innermost LAST (Python traceback order)."""
    frames: list[Frame] = []
    for raw in stack.splitlines():
        m = V8_FRAME.match(raw) or GECKO_FRAME.match(raw.strip())
        if not m:
            continue
        fn = (m.group("fn") or "<anonymous>").replace("async ", "").strip() or "<anonymous>"
        file = m.group("file")
        in_app = "node_modules" not in file and not file.startswith("node:")
        frames.append(
            Frame(function=fn, file=file, line=int(m.group("line")), col=int(m.group("col")), in_app=in_app)
        )
    frames.reverse()
    return frames


# ---- source maps (v3) -----------------------------------------------------------------------

B64 = {c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/")}


def _vlq(segment: str) -> list[int]:
    values: list[int] = []
    shift = value = 0
    for ch in segment:
        digit = B64[ch]
        value += (digit & 31) << shift
        if digit & 32:
            shift += 5
            continue
        values.append(-(value >> 1) if value & 1 else value >> 1)
        shift = value = 0
    return values


@dataclass
class SourceMap:
    sources: list[str]
    contents: list[str | None]
    names: list[str]
    # per generated line: sorted (gen_col, src_idx, src_line, src_col, name_idx|-1)
    lines: list[list[tuple[int, int, int, int, int]]] = field(
        default_factory=list[list[tuple[int, int, int, int, int]]]
    )

    @classmethod
    def parse(cls, raw: str) -> SourceMap:
        data = json.loads(raw)
        sm = cls(
            data["sources"],
            data.get("sourcesContent") or [None] * len(data["sources"]),
            data.get("names", []),
        )
        src = sline = scol = name = 0
        for line in data["mappings"].split(";"):
            gcol = 0
            segs: list[tuple[int, int, int, int, int]] = []
            for seg in filter(None, line.split(",")):
                v = _vlq(seg)
                gcol += v[0]
                if len(v) >= 4:
                    src += v[1]
                    sline += v[2]
                    scol += v[3]
                    n = -1
                    if len(v) >= 5:
                        name += v[4]
                        n = name
                    segs.append((gcol, src, sline, scol, n))
            sm.lines.append(segs)
        return sm

    def lookup(self, line: int, col: int) -> tuple[str, int, int, str | None] | None:
        """1-based generated line, 1-based column → (source, 1-based line, 1-based col, name)."""
        if not 1 <= line <= len(self.lines):
            return None
        segs = self.lines[line - 1]
        i = bisect_right([s[0] for s in segs], col - 1) - 1
        if i < 0:
            return None
        _, src, sline, scol, n = segs[i]
        return self.sources[src], sline + 1, scol + 1, (self.names[n] if n >= 0 else None)

    def source_text(self, source: str) -> str | None:
        try:
            return self.contents[self.sources.index(source)]
        except ValueError:
            return None


FUNC_DECL = [
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)\s*\("),
    re.compile(
        r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*(?::\s*[^=]+)?=>"
    ),
    re.compile(
        r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|async\s+|readonly\s+)*(\w+)\s*(?:=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*[^=]+)?=>|\([^)]*\)\s*(?::\s*[^{]+)?\{)"
    ),
]
KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "constructor", "function"}


def enclosing_function(source: str, line: int) -> str | None:
    """Best-effort name of the function containing a 1-based line of original source."""
    lines = source.splitlines()
    for i in range(min(line, len(lines)) - 1, -1, -1):
        if i < line - 1 and lines[i].startswith("}"):
            return None  # left the enclosing top-level block: the frame is a top-level callback
        for pattern in FUNC_DECL:
            m = pattern.match(lines[i])
            if m and m.group(1) not in KEYWORDS:
                return m.group(1)
    return None


def clean_source_path(source: str) -> str:
    path = re.sub(r"^(?:webpack|vite)?:?/*", "", source)
    while path.startswith("../"):
        path = path[3:]
    return path


MapFetcher = Callable[[str], str | None]


@lru_cache(maxsize=64)
def _cached_map(url: str, fetcher_id: int) -> SourceMap | None:  # fetcher_id keeps caches per fetcher
    raw = _FETCHERS[fetcher_id](url)
    return SourceMap.parse(raw) if raw else None


_FETCHERS: dict[int, MapFetcher] = {}


def symbolicate(frames: list[Frame], fetch_map: MapFetcher) -> tuple[list[Frame], bool]:
    """Map minified frames to original source via `<file>.map`. Returns (frames, any_mapped)."""
    _FETCHERS[id(fetch_map)] = fetch_map
    out: list[Frame] = []
    mapped = False
    for f in frames:
        if not f.file.endswith(".js") or f.line is None or f.col is None:
            out.append(f)
            continue
        sm = _cached_map(f.file + ".map", id(fetch_map))
        hit = sm.lookup(f.line, f.col) if sm else None
        if not sm or not hit:
            out.append(f)
            continue
        source, line, col, _name = hit
        text = sm.source_text(source)
        fn = (enclosing_function(text, line) if text else None) or f.function
        path = clean_source_path(source)
        out.append(Frame(function=fn, file=path, line=line, col=col, in_app="node_modules" not in path))
        mapped = True
    return out, mapped


# ---- fingerprints ---------------------------------------------------------------------------

HASHED_ASSET = re.compile(r"-[A-Za-z0-9_-]{6,}\.js$")
NUMBERS = re.compile(r"\b\d+\b|0x[0-9a-f]+|[0-9a-f]{8}-[0-9a-f-]{27}", re.I)


def normalize_frame(f: Frame) -> str:
    file = re.sub(r"^\w+://[^/]+", "", f.file)
    file = HASHED_ASSET.sub(".js", file)
    return f"{f.function}@{file.rsplit('/', 2)[-1] if '/' in file else file}"


def fingerprint(
    kind: str, app: str, error_type: str | None, frames: list[Frame], culprit: str | None, metric: str | None
) -> str:
    if kind in ("crash", "exception") and frames:
        in_app = [f for f in frames if f.in_app] or frames
        top = [normalize_frame(f) for f in in_app[-5:]]
        basis = [kind, app, error_type or "", *top]
    else:
        basis = [kind, app, error_type or "", metric or "", NUMBERS.sub("N", culprit or "")]
    return hashlib.sha1("|".join(basis).encode()).hexdigest()[:16]  # noqa: S324 - grouping key, not security
