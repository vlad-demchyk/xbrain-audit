"""A parameter must not take the name of a module the file imports.

Measured 2026-09-02, on a live site: `cli_impl.auditpass` imported `progress`
and `_audit_at_widths` had a parameter called `progress`. Inside that
function `progress.notice(...)` therefore meant "call `.notice` on the
callback", and the browser pass died with

    the browser pass failed: 'function' object has no attribute 'notice'

The suite was green through it, because every test that reaches that code
path mocks `_audit_at_widths` - so the one function where the two names met
was the one function never executed. Only a real run found it.

This is the general form of that, and it is cheap: read every module, list
what it imports at the top level, and fail on any function whose parameters
or assignments reuse one of those names. Shadowing is legal Python and
usually harmless; it is harmless right up to the first attribute access, and
by then the failure is somewhere else entirely.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: Directories that are not this project's code.
_SKIP = ("venv", "build", "dist", "__pycache__", ".git", "simulations",
         ".xaudit", ".xanalyze", "tests")

#: Names a local variable may legitimately reuse. `config` is the pattern
#: this codebase uses everywhere - `CrawlConfig` instances are called
#: `config` and the module is also `config` - and it is safe because those
#: functions do not reach for the module. Listed rather than silently
#: allowed, so adding to it is a decision somebody makes on purpose.
_ALLOWED = {"config", "json", "audit", "detectors", "report", "models",
            "suppression", "duplicates", "crawler", "devserver", "updater",
            "backups", "abbreviations", "replacements", "explanations",
            "diagnosis", "rewriter", "uninstaller"}


def _modules():
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in _SKIP for part in path.parts):
            continue
        yield path


def _imported_names(tree: ast.Module) -> set:
    """Module-level `import x` names only.

    `from x import y` binds `y`, which is a function or a class and shadowing
    it is a different (smaller) problem: calling a shadowed function fails at
    the call, in the same line, where it is obvious.
    """
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                names.add(bound)
    return names


def _local_bindings(func: ast.AST):
    """Every name this function binds: parameters and plain assignments."""
    args = func.args
    for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
        yield arg.arg, arg.lineno
    for extra in (args.vararg, args.kwarg):
        if extra is not None:
            yield extra.arg, extra.lineno
    for node in ast.walk(func):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            yield node.id, node.lineno


class NoModuleIsShadowedWhereItIsUsed(unittest.TestCase):

    def test_no_function_rebinds_a_module_its_file_imports(self):
        offenders = []
        for path in _modules():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover - compileall covers this
                continue
            imported = _imported_names(tree) - _ALLOWED
            if not imported:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for name, line in _local_bindings(node):
                    if name in imported:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{line} "
                            f"{node.name}() binds {name!r}, "
                            f"which is a module this file imports")
        self.assertEqual(offenders, [], "\n" + "\n".join(sorted(set(offenders))))


if __name__ == "__main__":
    unittest.main()
