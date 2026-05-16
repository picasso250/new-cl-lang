"""
BDD 测试套件 —— 自动收集 test_cases/ 下所有 .nc 文件。
用法:
  python tests/test_basic.py                    # 跑全部
  python tests/test_basic.py case_033_method.nc  # 跑单个
"""
import os
import sys
import glob
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler import compile_nc_to_c, run_c_code

CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "test_cases")


def _discover_cases():
    cases = []
    for path in sorted(glob.glob(os.path.join(CASE_DIR, "*.nc"))):
        with open(path, encoding="utf-8") as f:
            source = f.read()
        expected_lines = re.findall(r"#\s*STDOUT:\s*(.*)", source)
        expected = "\n".join(expected_lines) if expected_lines else None
        fname = os.path.basename(path)
        cases.append((fname, source, expected))
    return cases


def _compile_and_run(source: str) -> str:
    c_code = compile_nc_to_c(source)
    return run_c_code(c_code).strip()


def test_all_cases():
    for fname, source, expected in _discover_cases():
        actual = _compile_and_run(source)
        assert actual == expected, f"{fname}: expected '{expected}', got '{actual}'"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fname = sys.argv[1]
        path = os.path.join(CASE_DIR, fname) if not os.path.isabs(fname) else fname
        if not os.path.exists(path):
            print(f"File not found: {path}")
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            source = f.read()
        expected_lines = re.findall(r"#\s*STDOUT:\s*(.*)", source)
        expected = "\n".join(expected_lines) if expected_lines else None
        print(f"=== {fname} ===")
        actual = _compile_and_run(source)
        if expected is not None:
            print(f"expected: {repr(expected)}")
            print(f"actual:   {repr(actual)}")
            print("PASS" if actual == expected else "FAIL")
        else:
            print(f"output: {repr(actual)}")
    else:
        for fname, source, expected in _discover_cases():
            actual = _compile_and_run(source)
            status = "PASS" if actual == expected else "FAIL"
            if status == "FAIL":
                print(f"{status} {fname}: expected {repr(expected)}, got {repr(actual)}")
        print("done.")
