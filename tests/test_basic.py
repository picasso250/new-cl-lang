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
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler import compile_nc_sources_with_libs, run_llvm_ir

CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "test_cases")


def _discover_cases():
    cases = []
    for path in sorted(glob.glob(os.path.join(CASE_DIR, "*.nc"))):
        with open(path, encoding="utf-8") as f:
            source = f.read()
        expected = _parse_expected(source)
        fname = os.path.basename(path)
        cases.append((fname, source, expected))
    return cases


def _parse_expected(source: str) -> tuple[str, str, int]:
    error_lines = re.findall(r"#\s*ERROR:\s*(.*)", source)
    if error_lines:
        return ("__ERROR__", "\n".join(error_lines), 0)
    stdout_lines = re.findall(r"#\s*STDOUT:\s*(.*)", source)
    stderr_lines = re.findall(r"#\s*STDERR:\s*(.*)", source)
    rc_lines = re.findall(r"#\s*RC:\s*(-?\d+)", source)
    stdout = "\n".join(stdout_lines)
    stderr = "\n".join(stderr_lines)
    rc = int(rc_lines[-1]) if rc_lines else 0
    return stdout, stderr, rc


def _compile_and_run(source: str) -> tuple[str, str, int]:
    try:
        llvm_ir, link_libs = compile_nc_sources_with_libs([("<memory>", source)])
    except Exception as e:
        return "__ERROR__", str(e), 0
    stdout, stderr, rc = run_llvm_ir(llvm_ir, link_libs)
    return stdout.strip(), stderr.strip(), rc


def _case_ok(expected: tuple[str, str, int], actual: tuple[str, str, int]) -> bool:
    if expected[0] == "__ERROR__":
        return actual[0] == "__ERROR__" and expected[1] in actual[1]
    return actual == expected


def _run_case(case: tuple[str, str, tuple[str, str, int]]) -> tuple[str, tuple[str, str, int], tuple[str, str, int]]:
    fname, source, expected = case
    return fname, expected, _compile_and_run(source)


def _worker_count() -> int:
    override = os.environ.get("NC_TEST_BASIC_WORKERS")
    if override:
        try:
            count = int(override)
        except ValueError:
            raise RuntimeError("NC_TEST_BASIC_WORKERS must be an integer")
        if count < 1:
            raise RuntimeError("NC_TEST_BASIC_WORKERS must be >= 1")
        return count
    return max(1, min(32, os.cpu_count() or 1))


def _run_all_cases(cases):
    workers = _worker_count()
    if workers == 1:
        return [_run_case(case) for case in cases]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_run_case, cases))


def test_all_cases():
    for fname, expected, actual in _run_all_cases(_discover_cases()):
        if expected[0] == "__ERROR__":
            assert actual[0] == "__ERROR__", f"{fname}: expected error, got {actual}"
            assert expected[1] in actual[1], f"{fname}: expected error containing {expected[1]!r}, got {actual[1]!r}"
        else:
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
        expected = _parse_expected(source)
        print(f"=== {fname} ===")
        actual = _compile_and_run(source)
        print(f"expected: {repr(expected)}")
        print(f"actual:   {repr(actual)}")
        print("PASS" if actual == expected else "FAIL")
    else:
        passed = 0
        failed = 0
        for fname, expected, actual in _run_all_cases(_discover_cases()):
            ok = _case_ok(expected, actual)
            if ok:
                print(f"  PASS  {fname}")
                passed += 1
            else:
                print(f"  FAIL  {fname}: expected {repr(expected)}, got {repr(actual)}")
                failed += 1
        print(f"\n{passed} passed, {failed} failed.")
