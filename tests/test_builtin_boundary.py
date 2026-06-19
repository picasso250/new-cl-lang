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


def test_std_module_builtins_are_explicitly_bounded():
    source = _read("compiler/builtins.py")

    assert 'name in {"io.print", "io.println"}' in source
    assert 'name == "fs.read_file"' not in source
    assert 'name == "fs.write_file"' not in source
    assert 'name == "fs.exists"' not in source
    assert 'name == "fs.remove"' not in source
    assert 'name == "fs.rename"' not in source
    assert 'name == "fs.mkdir"' not in source
    assert 'name == "os.args"' not in source
    assert 'name == "os.getenv"' not in source
    assert 'name == "os.has_env"' not in source
    assert 'name == "os.cwd"' not in source
    assert 'name == "os.exit"' not in source
    assert 'name == "strings.contains"' not in source
    assert 'name == "strings.starts_with"' not in source
    assert 'name == "strings.ends_with"' not in source
    assert 'name == "strings.index"' not in source
    assert 'name == "runtime.gc_collect"' in source
    assert 'name == "runtime.gc_live"' in source
    assert 'name == "cap"' in source
    assert 'name == "copy"' in source
    assert 'name == "clear"' in source
    assert 'name == "delete"' in source
    assert 'name == "map_has"' not in source
    assert 'name in {"min", "max"}' in source
    assert 'name == "abs"' in source
    assert 'name == "print"' not in source
    assert 'name == "read_file"' not in source
    assert 'name == "write_file"' not in source
    assert 'name == "gc_collect"' not in source
    assert 'name == "gc_live"' not in source


def test_llvm_declares_external_ncrt_symbols():
    source = _read("compiler/llvm_runtime.py")

    assert "__nc_gc_alloc" in source
    assert "__nc_read_file" not in source
    assert "__nc_fs_exists" not in source
    assert "__nc_str_contains" not in source
    assert "__nc_map_init" in source
