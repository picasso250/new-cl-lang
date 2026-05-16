"""
BDD 测试套件 —— 自动收集 test_cases/ 下所有 .nc 文件。
每个文件第一行注释 # STDOUT: <期望输出> 定义期望值。
"""
import os
import sys
import glob
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler import compile_nc_to_c, run_c_code

CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "test_cases")


def _discover_cases():
    """扫描 test_cases/*.nc，提取 (文件名, nc源码, 期望输出)。"""
    cases = []
    for path in sorted(glob.glob(os.path.join(CASE_DIR, "*.nc"))):
        with open(path, encoding="utf-8") as f:
            source = f.read()
        expected = None
        for line in source.split("\n"):
            m = re.match(r"#\s*STDOUT:\s*(.*)", line)
            if m:
                expected = m.group(1).strip()
                break
        fname = os.path.basename(path)
        cases.append((fname, source, expected))
    return cases


def _compile_and_run(source: str) -> str:
    c_code = compile_nc_to_c(source)
    return run_c_code(c_code).strip()


def test_all_cases():
    """自动发现并运行所有 test_cases。"""
    for fname, source, expected in _discover_cases():
        actual = _compile_and_run(source)
        assert actual == expected, f"{fname}: expected '{expected}', got '{actual}'"
