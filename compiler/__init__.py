"""
NC Compiler —— 编译 NC 源码到 C，再调用系统 C 编译器生成可执行文件。
"""
import subprocess
import tempfile
import os

from compiler.lexer import lex
from compiler.parser import parse
from compiler.ast import Program
from compiler.codegen import generate_c


def compile_nc_to_c(nc_source: str) -> str:
    """NC 源码 → C 源码。"""
    tokens = list(lex(nc_source))
    ast: Program = parse(tokens)
    return generate_c(ast)


def run_c_code(c_code: str) -> str:
    """C 源码 → 编译 → 运行 → 返回 stdout。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        c_path = os.path.join(tmpdir, "out.c")
        exe_path = os.path.join(tmpdir, "out.exe")

        with open(c_path, "w", encoding="utf-8") as f:
            f.write(c_code)

        # 编译 C → 可执行文件
        result = subprocess.run(
            ["gcc", c_path, "-o", exe_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            # 尝试 clang
            result = subprocess.run(
                ["clang", c_path, "-o", exe_path],
                capture_output=True, text=True
            )
        if result.returncode != 0:
            raise RuntimeError(f"C compilation failed:\n{result.stderr}")

        # 运行
        result = subprocess.run(
            [exe_path],
            capture_output=True, text=True
        )
        return result.stdout
