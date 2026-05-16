"""
BDD 测试套件 —— 从最简单 case 开始，逐条打通全链路。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler import compile_nc_to_c, run_c_code

CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "test_cases")


def compile_and_run(nc_source: str) -> str:
    c_code = compile_nc_to_c(nc_source)
    return run_c_code(c_code)


def _run_case(filename: str):
    path = os.path.join(CASE_DIR, filename)
    with open(path, encoding="utf-8") as f:
        source = f.read()
    return compile_and_run(source).strip()


def test_case_001():
    assert _run_case("case_001_print_add.nc") == "3"

def test_case_002_add():
    assert _run_case("case_002_add.nc") == "8"

def test_case_003_sub():
    assert _run_case("case_003_sub.nc") == "6"

def test_case_004_mul():
    assert _run_case("case_004_mul.nc") == "21"

def test_case_005_div():
    assert _run_case("case_005_div.nc") == "5"

def test_case_006_mod():
    assert _run_case("case_006_mod.nc") == "1"

def test_case_007_let():
    assert _run_case("case_007_let.nc") == "42"
