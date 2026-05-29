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
    assert 'node.name == "io.println"' not in source
    assert 'node.name == "read_file"' not in source
    assert 'node.name == "append"' not in source


def test_io_println_is_the_only_output_builtin():
    source = _read("compiler/builtins.py")

    assert 'name == "io.println"' in source
    assert 'name == "print"' not in source


def test_llvm_declares_external_ncrt_symbols():
    source = _read("compiler/llvm_codegen.py")

    assert "__nc_gc_alloc" in source
    assert "__nc_read_file" in source
    assert "__nc_map_new" in source
