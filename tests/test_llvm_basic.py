"""LLVM experimental backend smoke tests for the supported i32/bool subset."""

import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler import compile_nc_to_llvm_ir, run_llvm_code


CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "test_cases")
LLVM_CASES = {
    "case_001_print_add.nc",
    "case_002_add.nc",
    "case_003_sub.nc",
    "case_004_mul.nc",
    "case_005_div.nc",
    "case_006_mod.nc",
    "case_007_let.nc",
    "case_008_multi_let.nc",
    "case_009_reassign.nc",
    "case_010_var_expr.nc",
    "case_011_if.nc",
    "case_012_while.nc",
    "case_013_fun.nc",
}


def _parse_expected(source: str) -> tuple[str, str, int]:
    stdout_lines = re.findall(r"#\s*STDOUT:\s*(.*)", source)
    stderr_lines = re.findall(r"#\s*STDERR:\s*(.*)", source)
    rc_lines = re.findall(r"#\s*RC:\s*(-?\d+)", source)
    stdout = "\n".join(stdout_lines)
    stderr = "\n".join(stderr_lines)
    rc = int(rc_lines[-1]) if rc_lines else 0
    return stdout, stderr, rc


def _discover_cases():
    cases = []
    for path in sorted(glob.glob(os.path.join(CASE_DIR, "*.nc"))):
        fname = os.path.basename(path)
        if fname not in LLVM_CASES:
            continue
        with open(path, encoding="utf-8") as f:
            source = f.read()
        cases.append((fname, source, _parse_expected(source)))
    return cases


def _compile_and_run(source: str) -> tuple[str, str, int]:
    ir_code = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_code(ir_code)
    return stdout.strip(), stderr.strip(), rc


def test_llvm_cases():
    for fname, source, expected in _discover_cases():
        actual = _compile_and_run(source)
        assert actual == expected, f"{fname}: expected {expected!r}, got {actual!r}"


def test_llvm_i32_return_call():
    source = """
    # STDOUT: 7
    fun add(a: i32, b: i32): i32 { return a + b }
    fun main() { print(add(3, 4)) }
    """
    assert _compile_and_run(source) == _parse_expected(source)


if __name__ == "__main__":
    passed = 0
    failed = 0
    for fname, source, expected in _discover_cases():
        actual = _compile_and_run(source)
        if actual == expected:
            print(f"  PASS  {fname}")
            passed += 1
        else:
            print(f"  FAIL  {fname}: expected {expected!r}, got {actual!r}")
            failed += 1
    extra = """
    # STDOUT: 7
    fun add(a: i32, b: i32): i32 { return a + b }
    fun main() { print(add(3, 4)) }
    """
    if _compile_and_run(extra) == _parse_expected(extra):
        print("  PASS  llvm_i32_return_call")
        passed += 1
    else:
        print("  FAIL  llvm_i32_return_call")
        failed += 1
    print(f"\n{passed} passed, {failed} failed.")
    sys.exit(1 if failed else 0)
