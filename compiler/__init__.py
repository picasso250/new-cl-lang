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


def compile_nc_sources_to_c(sources: "list[tuple[str, str]]") -> str:
    """多个 NC 源码片段 → 单个 C 源码。

    当前语义是同一模块内多文件自动互见：所有文件解析后合并为一个 Program，
    再走同一套三 pass。
    """
    statements = []
    combined_source_parts = []
    for filename, source in sources:
        tokens = list(lex(source))
        ast: Program = parse(tokens)
        statements.extend(ast.statements)
        combined_source_parts.append(source)

    program = Program(statements)
    combined_source = "\n".join(combined_source_parts)

    # Pass 1: 建符号表
    symtab = build_symbol_table(program)

    # Pass 2: 类型推断
    infer_types(program, symtab, combined_source)

    # Pass 3: 代码生成
    return generate_c(program)


def compile_nc_to_c(nc_source: str) -> str:
    """NC 源码 → C 源码（三 pass）。"""
    return compile_nc_sources_to_c([("<memory>", nc_source)])


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


def build_c_code(c_code: str, out_dir: str, name: str = "main") -> "tuple[str, str]":
    """C 源码 → build 目录产物，返回 (c_path, exe_path)。"""
    os.makedirs(out_dir, exist_ok=True)
    c_path = os.path.join(out_dir, f"{name}.c")
    exe_path = os.path.join(out_dir, f"{name}.exe")

    with open(c_path, "w", encoding="utf-8") as f:
        f.write(c_code)

    result = subprocess.run(
        ["gcc", c_path, "-o", exe_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"C compilation failed:\n{result.stderr}")

    return c_path, exe_path
