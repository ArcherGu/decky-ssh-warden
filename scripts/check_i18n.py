#!/usr/bin/env python3
"""Check that every backend error code has a translation in both languages of src/i18n.ts.

The typecheck catches a code that English has and Chinese lacks, but not a code the backend
raises that neither language knows; the panel would then show the English fallback text.
Run from the repository root: python3 scripts/check_i18n.py
"""
import ast
import glob
import re
import sys


def backend_codes() -> dict[str, str]:
    """UserError codes raised in py_modules/sshwarden, with where each one is raised."""
    codes: dict[str, str] = {}
    for path in sorted(glob.glob("py_modules/sshwarden/*.py")):
        for node in ast.walk(ast.parse(open(path, encoding="utf-8").read(), path)):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            first, func = node.args[0], node.func
            # UserError("code", ...) and subclasses calling super().__init__("code", ...)
            is_user_error = isinstance(func, ast.Name) and func.id == "UserError"
            is_subclass_init = isinstance(func, ast.Attribute) and func.attr == "__init__"
            if (is_user_error or is_subclass_init) and isinstance(first, ast.Constant) and isinstance(first.value, str):
                codes.setdefault(first.value, f"{path}:{node.lineno}")
    return codes


def translated_codes() -> dict[str, set[str]]:
    """The keys of each `errors: { ... }` table in src/i18n.ts, in order: English, Chinese."""
    source = open("src/i18n.ts", encoding="utf-8").read()
    tables = re.findall(r"\n  errors: \{\n(.*?)\n  \}", source, re.S)
    if len(tables) != 2:
        sys.exit(f"expected 2 errors tables in src/i18n.ts, found {len(tables)}")
    return {lang: set(re.findall(r"^    ([a-z_]+):", table, re.M)) for lang, table in zip(("en", "zhCN"), tables)}


def main() -> int:
    codes = backend_codes()
    problems = []
    for lang, keys in translated_codes().items():
        problems += [f"{lang}: no translation for {code} ({where})" for code, where in sorted(codes.items()) if code not in keys]
        problems += [f"{lang}: {key} is translated but never raised" for key in sorted(keys - codes.keys())]
    for problem in problems:
        print(problem, file=sys.stderr)
    if not problems:
        print(f"all {len(codes)} backend error codes are translated in both languages")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
