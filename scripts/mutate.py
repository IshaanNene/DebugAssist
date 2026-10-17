"""A small mutation tester (ROADMAP-100 022): does each test file notice when its module's logic is broken?

    uv run python scripts/mutate.py <module.py> <test file> [<test file> …]

Each mutant changes one thing in the module — a comparison flipped (`==`/`!=`, `<`/`>=`, `in`/`not in`), `and`/`or`
swapped, a `not` dropped, a condition negated, a boolean or number constant changed, a string constant emptied —
and the tests run against it (one process per mutant, stopping at the first failure). A mutant the tests do not
fail on "survives" and is printed with its line. The score is killed / total. The module file is restored after
every mutant, also on Ctrl-C.
"""

from __future__ import annotations

import ast
import copy
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Gt: ast.LtE,
        ast.LtE: ast.Gt, ast.In: ast.NotIn, ast.NotIn: ast.In, ast.Is: ast.IsNot, ast.IsNot: ast.Is}  # fmt: skip


def _docstrings(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            first = body[0]
            if isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def mutants(source: str) -> Iterator[tuple[int, str, str]]:
    """(line, description, mutated source) for every single-point mutation of the module."""
    tree = ast.parse(source)
    skip = _docstrings(tree)
    targets = [n for n in ast.walk(tree)]
    for index, node in enumerate(targets):
        options: list[tuple[str, ast.AST]] = []
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in FLIP:
                    new = copy.deepcopy(node)
                    new.ops[i] = FLIP[type(op)]()
                    options.append((f"{type(op).__name__} → {FLIP[type(op)].__name__}", new))
        elif isinstance(node, ast.BoolOp):
            new = copy.deepcopy(node)
            new.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
            options.append(("and ↔ or", new))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            options.append(("drop not", copy.deepcopy(node.operand)))
        elif isinstance(node, ast.If | ast.IfExp):
            new = copy.deepcopy(node)
            new.test = ast.UnaryOp(op=ast.Not(), operand=new.test)
            options.append(("negate condition", new))
        elif isinstance(node, ast.Constant) and id(node) not in skip:
            v = node.value
            if isinstance(v, bool):
                options.append((f"{v} → {not v}", ast.Constant(not v)))
            elif isinstance(v, int | float) and not isinstance(v, bool):
                options.append((f"{v} → {v + 1}", ast.Constant(v + 1)))
            elif isinstance(v, str) and v:
                options.append((f"{v[:30]!r} → ''", ast.Constant("")))
        for desc, replacement in options:
            mutated = _replace(tree, index, replacement)
            if mutated is not None:
                yield getattr(node, "lineno", 0), desc, mutated


def _replace(tree: ast.AST, index: int, replacement: ast.AST) -> str | None:
    clone = copy.deepcopy(tree)
    nodes = list(ast.walk(clone))
    target = nodes[index]
    for parent in ast.walk(clone):
        for field, value in ast.iter_fields(parent):
            if value is target:
                setattr(parent, field, replacement)
                return _unparse(clone)
            if isinstance(value, list) and target in value:
                value[value.index(target)] = replacement
                return _unparse(clone)
    return None


def _unparse(tree: ast.AST) -> str | None:
    try:
        return ast.unparse(ast.fix_missing_locations(tree))
    except (ValueError, TypeError):
        return None


def main(module: str, tests: list[str]) -> int:
    path = Path(module)
    original = path.read_text()
    survivors: list[str] = []
    total = killed = 0
    try:
        for line, desc, source in mutants(original):
            total += 1
            path.write_text(source)
            r = subprocess.run(  # noqa: S603 - this interpreter running pytest on the caller's test files
                [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests],
                capture_output=True,
                check=False,
            )
            if r.returncode == 0:
                survivors.append(f"{path.name}:{line}: {desc}")
            else:
                killed += 1
    finally:
        path.write_text(original)
    for s in survivors:
        print("survived", s)
    score = killed / total if total else 1.0
    print(f"{killed}/{total} mutants killed ({score:.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2:]))
