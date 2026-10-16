"""Call variations — a mechanical check of a fix's width (DA_CALL_VARIANTS=1), Python only, no model.

A report shows one call. Python lets a caller make the same call other ways — keyword instead of positional
arguments, through the instance instead of the class — and a fix that makes only the reported spelling work is
narrower than the bug. From the report's own code this derives, for each call of a method the snippet defines, the
other spellings of the same call, and builds one small program per spelling: the snippet's statements up to that
call, then the call, printing its result's repr or the exception's type. With the fix, every spelling must print
what the reported spelling prints.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

_CODE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.S)
MARK = "DA-VARIANT"


@dataclass(frozen=True)
class Variant:
    label: str  # e.g. "keyword arguments"
    call: str  # the call as written in this variant
    program: str


def snippets(report: str) -> list[str]:
    """The report's Python code blocks that parse."""
    out: list[str] = []
    for code in _CODE.findall(report):
        try:
            ast.parse(code)
        except SyntaxError:
            continue
        out.append(code)
    return out


def _methods(tree: ast.Module) -> dict[str, dict[str, list[str]]]:
    """class → method → positional parameter names (incl. self) for plain methods without *args/**kwargs."""
    out: dict[str, dict[str, list[str]]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            a = item.args
            static = any(
                isinstance(d, ast.Name) and d.id in {"staticmethod", "classmethod"}
                for d in item.decorator_list
            )
            if static or a.vararg or a.kwarg or a.posonlyargs or a.kwonlyargs:
                continue
            out.setdefault(node.name, {})[item.name] = [p.arg for p in a.args]
    return out


def _instances(tree: ast.Module, classes: set[str]) -> dict[str, str]:
    """name → class for `name = Class(...)` at the top level."""
    out: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in classes
        ):
            out[node.targets[0].id] = node.value.func.id
    return out


def _probe(prefix: list[ast.stmt], call: str) -> str:
    head = ast.unparse(ast.Module(body=prefix, type_ignores=[]))
    return (
        f"{head}\n"
        "try:\n"
        f"    __da = ('ok', repr({call}))\n"
        "except Exception as __e:\n"
        "    __da = ('raises', type(__e).__name__)\n"
        f"print({MARK!r}, __da)\n"
    )


def _spellings(cls: str, inst: str, method: str, params: list[str], args: list[str]) -> list[tuple[str, str]]:
    """Every other way to write the call `cls.method(inst, *args)` (same binding), as (label, call)."""
    rest = params[1:]
    kw = ", ".join(f"{p}={a}" for p, a in zip(rest, args, strict=True))
    pos = ", ".join(args)
    out = [
        ("through the class, positional", f"{cls}.{method}({', '.join([inst, *args])})"),
        (
            "through the class, keyword arguments",
            f"{cls}.{method}({', '.join([f'{params[0]}={inst}', *[f'{p}={a}' for p, a in zip(rest, args, strict=True)]])})",
        ),
        ("through the instance, positional", f"{inst}.{method}({pos})"),
    ]
    if args:
        out.append(
            ("through the class, instance positional, the rest by keyword", f"{cls}.{method}({inst}, {kw})")
        )
        out.append(("through the instance, keyword arguments", f"{inst}.{method}({kw})"))
    return out


def variants(snippet: str) -> list[tuple[Variant, list[Variant]]]:
    """For each call of a snippet-defined method (with plain positional/keyword arguments): the call as reported,
    and its other spellings. Empty when nothing applies."""
    tree = ast.parse(snippet)
    methods = _methods(tree)
    instances = _instances(tree, set(methods))
    out: list[tuple[Variant, list[Variant]]] = []
    seen: set[str] = set()
    for k, stmt in enumerate(tree.body):
        for node in ast.walk(stmt):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if not isinstance(node.func.value, ast.Name) or any(
                isinstance(a, ast.Starred) for a in node.args
            ):
                continue
            if any(kw.arg is None for kw in node.keywords):
                continue
            owner, method = node.func.value.id, node.func.attr
            cls = owner if owner in methods else instances.get(owner)
            if cls is None or method not in methods[cls]:
                continue
            params = methods[cls][method]
            given = [ast.unparse(a) for a in node.args]
            named = {kw.arg: ast.unparse(kw.value) for kw in node.keywords if kw.arg}
            if owner == cls:  # through the class: the instance is the first argument
                bound = dict(zip(params, given, strict=False))
            else:
                bound = {params[0]: owner, **dict(zip(params[1:], given, strict=False))}
            bound.update(named)
            if set(bound) != set(params) or not isinstance(
                ast.parse(bound[params[0]], mode="eval").body, ast.Name
            ):
                continue  # defaults left out, or an instance that is not a plain name: no safe re-spelling
            inst, args = bound[params[0]], [bound[p] for p in params[1:]]
            reported = ast.unparse(node)
            if reported in seen:
                continue
            seen.add(reported)
            prefix = tree.body[:k]
            base = Variant("as reported", reported, _probe(prefix, reported))
            others = [
                Variant(label, call, _probe(prefix, call))
                for label, call in _spellings(cls, inst, method, params, args)
                if ast.unparse(ast.parse(call, mode="eval").body) != reported
            ]
            out.append((base, others))
    return out


def result(output: str) -> str | None:
    """The probe's printed outcome, e.g. "('ok', '6')" or "('raises', 'TypeError')"; None if it did not run."""
    for line in output.splitlines():
        if line.startswith(MARK):
            return line[len(MARK) :].strip()
    return None
