"""Guardrails for the temporary builtin boundary."""

import os

from compiler import compile_nc_to_c


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


def test_codegen_uses_builtin_boundary():
    source = _read("compiler/codegen.py")

    assert "lower_builtin_expr(" in source
    assert "lower_builtin_stmt(" in source
    assert 'node.name == "read_file"' not in source
    assert 'expr.name == "print"' not in source
    assert 'expr.name == "io.println"' not in source


def test_c_output_includes_ncrt_without_inline_runtime():
    generated = compile_nc_to_c("import io\nfun main() { io.println(str(1)) }\n")

    assert '#include "ncrt.h"' in generated
    assert "static void* __nc_gc_alloc" not in generated
    assert "typedef struct _nc_record" not in generated
    assert "static str __nc_i32_to_str" not in generated


def test_io_println_is_the_only_output_builtin():
    source = _read("compiler/builtins.py")

    assert 'name == "io.println"' in source
    assert 'name == "print"' not in source
