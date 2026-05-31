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
    assert 'node.name == "delete"' not in source


def test_io_output_builtins_are_std_module_qualified():
    source = _read("compiler/builtins.py")

    assert 'name in {"io.print", "io.println"}' in source
    assert 'name == "fs.read_file"' in source
    assert 'name == "fs.write_file"' in source
    assert 'name == "fs.exists"' in source
    assert 'name == "fs.remove"' in source
    assert 'name == "fs.rename"' in source
    assert 'name == "fs.mkdir"' in source
    assert 'name == "os.args"' in source
    assert 'name == "os.getenv"' in source
    assert 'name == "os.has_env"' in source
    assert 'name == "os.cwd"' in source
    assert 'name == "os.exit"' in source
    assert 'name == "runtime.gc_collect"' in source
    assert 'name == "runtime.gc_live"' in source
    assert 'name == "cap"' in source
    assert 'name == "copy"' in source
    assert 'name == "clear"' in source
    assert 'name == "delete"' in source
    assert 'name in {"min", "max"}' in source
    assert 'name == "abs"' in source
    assert 'name == "print"' not in source
    assert 'name == "read_file"' not in source
    assert 'name == "write_file"' not in source
    assert 'name == "gc_collect"' not in source
    assert 'name == "gc_live"' not in source


def test_llvm_declares_external_ncrt_symbols():
    source = _read("compiler/llvm_codegen.py")

    assert "__nc_gc_alloc" in source
    assert "__nc_read_file" in source
    assert "__nc_fs_exists" in source
    assert "__nc_map_init" in source
