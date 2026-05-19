"""
NC Compiler —— 三 pass 流水线：建符号表 → 类型推断 → 生成 C 代码。
"""
import subprocess
import tempfile
import os

from compiler.lexer import lex
from compiler.parser import parse
from compiler.ast import Program
from compiler.symtab import build_symbol_table
from compiler.typecheck import infer_types
from compiler.codegen import generate_c


def compile_nc_to_c(nc_source: str) -> str:
    """NC 源码 → C 源码（三 pass）。"""
    tokens = list(lex(nc_source))
    ast: Program = parse(tokens)

    # Pass 1: 建符号表
    symtab = build_symbol_table(ast)

    # Pass 2: 类型推断
    infer_types(ast, symtab, nc_source)

    # Pass 3: 代码生成
    return generate_c(ast)


def run_c_code(c_code: str) -> "tuple[str, str, int]":
    """C 源码 → 编译 → 运行 → 返回 (stdout, stderr, returncode)。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        c_path = os.path.join(tmpdir, "out.c")
        exe_path = os.path.join(tmpdir, "out.exe")

        with open(c_path, "w", encoding="utf-8") as f:
            f.write(c_code)

        result = subprocess.run(
            ["gcc", c_path, "-o", exe_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"C compilation failed:\n{result.stderr}")

        result = subprocess.run(
            [exe_path],
            capture_output=True, text=True
        )
        return result.stdout, result.stderr, result.returncode
