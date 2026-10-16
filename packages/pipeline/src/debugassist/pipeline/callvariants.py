"""Call variations — a mechanical check of a fix's width (DA_CALL_VARIANTS=1), Python only, no model.

A report shows one call. Python lets a caller make the same call other ways — keyword instead of positional
arguments, through the instance instead of the class — and a fix that makes only the reported spelling work is
narrower than the bug. From the report's own code (fenced blocks, REPL sessions included) this derives the other
spellings of each call and builds one small program per spelling: the snippet's statements up to that call, then
the call, printing its result (iterators by what they yield, addresses removed) or the exception's type. With the
fix, every spelling must print what the reported spelling prints.

Two kinds of call are spelled:
- a method the snippet defines (its parameters are in the snippet): keyword, mixed, through the instance or class;
- a library call — a name imported from outside the standard library, or a variable assigned from such a call: its
  parameters are only known at run time, so the program binds the reported arguments with `inspect.signature` and
  writes the call with every argument it can by keyword, or by position.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass

_CODE = re.compile(r"```([\w+-]*)[ \t]*\n(.*?)```", re.S)
_PY = {"", "python", "py", "python3", "pycon", "pytb", "ipython"}
MARK = "DA-VARIANT"
CALL_MARK = "DA-VARIANT-CALL"
# Printed result: iterators by (up to 20 of) what they yield, nested; reprs without memory addresses.
_NORM = (
    "def __da_norm(v, d=0):\n"
    "    import re\n"
    "    if d < 3 and hasattr(v, '__next__'):\n"
    "        return [__da_norm(x, d + 1) for x, _ in zip(v, range(20))]\n"
    "    if d < 3 and isinstance(v, list | tuple):\n"
    "        return [__da_norm(x, d + 1) for x in v]\n"
    "    return re.sub(r' at 0x[0-9a-fA-F]+', '', repr(v))\n"
)


@dataclass(frozen=True)
class Variant:
    label: str  # e.g. "keyword arguments"
    call: str  # the call as written in this variant
    program: str


def _repl(code: str) -> str:
    """A REPL session's input lines (`>>> `, `... `), outputs dropped; other code unchanged."""
    lines = code.splitlines()
    if not any(line.startswith(">>>") for line in lines):
        return code
    out: list[str] = []
    for line in lines:
        if line.startswith((">>> ", "... ")):
            out.append(line[4:])
        elif line.rstrip() in {">>>", "..."}:
            out.append("")
    return "\n".join(out) + "\n"


def session(report: str) -> str | None:
    """The report's code blocks as one session, in order (a later block may use an earlier block's imports);
    None when they do not parse together."""
    blocks = snippets(report)
    if not blocks:
        return None
    code = "\n".join(blocks)
    try:
        ast.parse(code)
    except SyntaxError:
        return None
    return code


def snippets(report: str) -> list[str]:
    """The report's Python code blocks (REPL sessions as their input lines) that parse."""
    out: list[str] = []
    for lang, code in _CODE.findall(report):
        if lang.lower() not in _PY:
            continue
        code = _repl(code)
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


def _head(prefix: list[ast.stmt]) -> str:
    """The statements before the call, each allowed to fail (a report's earlier lines may show the bug raising)."""
    lines: list[str] = []
    for stmt in prefix:
        if isinstance(
            stmt, ast.Import | ast.ImportFrom | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        ):
            lines.append(ast.unparse(stmt))
        else:
            body = "\n".join("    " + line for line in ast.unparse(stmt).splitlines())
            lines.append(f"try:\n{body}\nexcept Exception:\n    pass")
    return "\n".join(lines) + "\n" + _NORM


def _probe(prefix: list[ast.stmt], call: str) -> str:
    return (
        _head(prefix) + "try:\n"
        f"    __da = ('ok', repr(__da_norm({call})))\n"
        "except Exception as __e:\n"
        "    __da = ('raises', type(__e).__name__)\n"
        f"print({MARK!r}, __da)\n"
    )


def _library_probe(prefix: list[ast.stmt], node: ast.Call, mode: str) -> str:
    """The call re-spelled at run time: its reported arguments bound to the callee's signature, then every argument
    that can be passed by keyword (mode "keyword") or by position ("positional") written that way. Prints the call
    it made, then its result — or ('same',) when the spelling is the reported one, ('unspellable',) when the
    callee has no signature or the arguments do not bind."""
    func = ast.unparse(node.func)
    args = [ast.unparse(a) for a in node.args]
    kwargs = {k.arg: ast.unparse(k.value) for k in node.keywords if k.arg}
    return (
        _head(prefix)
        + "import inspect as __da_i\n"
        + f"__da_args, __da_kw, __da_mode = {args!r}, {kwargs!r}, {mode!r}\n"
        + "class __DaM:\n"
        "    def __init__(self, src):\n"
        "        self.src = src\n"
        "try:\n"
        f"    __da_sig = __da_i.signature({func})\n"
        "    __da_b = __da_sig.bind(*[__DaM(a) for a in __da_args], **{k: __DaM(v) for k, v in __da_kw.items()})\n"
        "except (TypeError, ValueError):\n"
        f"    print({MARK!r}, ('unspellable',))\n"
        "    raise SystemExit(0)\n"
        "__P = __da_i.Parameter\n"
        "__da_pos, __da_named = [], []\n"
        "__da_star = any(__da_sig.parameters[n].kind is __P.VAR_POSITIONAL and v for n, v in __da_b.arguments.items())\n"
        "for __n, __v in __da_b.arguments.items():\n"
        "    __kind = __da_sig.parameters[__n].kind\n"
        "    if __kind is __P.POSITIONAL_ONLY:\n"
        "        __da_pos.append(__v.src)\n"
        "    elif __kind is __P.VAR_POSITIONAL:\n"
        "        __da_pos.extend(m.src for m in __v)\n"
        "    elif __kind is __P.VAR_KEYWORD:\n"
        "        __da_named.extend(f'{k}={m.src}' for k, m in __v.items())\n"
        "    elif __kind is __P.KEYWORD_ONLY or (__da_mode == 'keyword' and not __da_star):\n"
        "        __da_named.append(f'{__n}={__v.src}')\n"
        "    else:\n"
        "        __da_pos.append(__v.src)\n"
        f"__da_call = {func!r} + '(' + ', '.join(__da_pos + __da_named) + ')'\n"
        f"if __da_pos == __da_args and __da_named == [f'{{k}}={{v}}' for k, v in __da_kw.items()]:\n"
        f"    print({MARK!r}, ('same',))\n"
        "    raise SystemExit(0)\n"
        f"print({CALL_MARK!r}, __da_call)\n"
        "try:\n"
        "    __da = ('ok', repr(__da_norm(eval(__da_call))))\n"
        "except Exception as __e:\n"
        "    __da = ('raises', type(__e).__name__)\n"
        f"print({MARK!r}, __da)\n"
    )


def _root(expr: ast.expr) -> str | None:
    while isinstance(expr, ast.Attribute | ast.Call | ast.Subscript):
        expr = expr.func if isinstance(expr, ast.Call) else expr.value
    return expr.id if isinstance(expr, ast.Name) else None


def _library_names(tree: ast.Module) -> set[str]:
    """Names bound by imports from outside the standard library, and top-level variables assigned from calls on
    them (e.g. `v = semver.Version.parse(...)`)."""
    std = set(sys.stdlib_module_names)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in std:
                    names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            if node.module.split(".")[0] not in std:
                names.update(a.asname or a.name for a in node.names)
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and _root(node.value) in names
        ):
            names.add(node.targets[0].id)
    return names


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
    library = _library_names(tree) - set(methods) - set(instances)
    out: list[tuple[Variant, list[Variant]]] = []
    seen: set[str] = set()
    for k, stmt in enumerate(tree.body):
        if isinstance(
            stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Import | ast.ImportFrom
        ):
            continue  # calls in a definition run when it is called, not here
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            if (
                _root(node.func) in library
                and (node.args or node.keywords)
                and not any(isinstance(a, ast.Starred) for a in node.args)
                and all(kw.arg for kw in node.keywords)
            ):
                reported = ast.unparse(node)
                if reported not in seen:
                    seen.add(reported)
                    prefix = tree.body[:k]
                    out.append(
                        (
                            Variant("as reported", reported, _probe(prefix, reported)),
                            [
                                Variant(
                                    f"{mode} arguments",
                                    f"{reported} with {mode} arguments",
                                    _library_probe(prefix, node, mode),
                                )
                                for mode in ("keyword", "positional")
                            ],
                        )
                    )
                continue
            if not isinstance(node.func, ast.Attribute):
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
    """The probe's printed outcome, e.g. "('ok', '6')", "('raises', 'TypeError')", "('same',)" (a library spelling
    that is the reported one) or "('unspellable',)"; None if it did not run."""
    for line in output.splitlines():
        if line.startswith(MARK + " "):
            return line[len(MARK) :].strip()
    return None


def spelled(output: str) -> str | None:
    """The call a library probe made, as it wrote it."""
    for line in output.splitlines():
        if line.startswith(CALL_MARK + " "):
            return line[len(CALL_MARK) :].strip()
    return None
