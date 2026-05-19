"""Guardrails for the temporary builtin boundary."""

import os


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(path: str) -> str:
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def test_typecheck_uses_builtin_boundary():
    source = _read("compiler/typecheck.py")

    assert "infer_builtin_call(" in source
    assert 'node.name == "print"' not in source
    assert 'node.name == "read_file"' not in source
    assert 'node.name == "append"' not in source


def test_codegen_uses_builtin_boundary():
    source = _read("compiler/codegen.py")

    assert "lower_builtin_expr(" in source
    assert "lower_builtin_stmt(" in source
    assert 'node.name == "read_file"' not in source
    assert 'expr.name == "print"' not in source
