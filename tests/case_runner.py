import glob
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler import compile_nc_sources_with_libs, run_llvm_ir


Expected = tuple[str, str, int]
Case = tuple[str, str, Expected]


def discover_cases(case_dir: str) -> list[Case]:
    cases = []
    for path in sorted(glob.glob(os.path.join(case_dir, "*.nc"))):
        with open(path, encoding="utf-8") as f:
            source = f.read()
        expected = parse_expected(source)
        fname = os.path.basename(path)
        cases.append((fname, source, expected))
    return cases


def parse_expected(source: str) -> Expected:
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


def compile_and_run(source: str) -> Expected:
    try:
        llvm_ir, link_libs = compile_nc_sources_with_libs([("<memory>", source)])
    except Exception as e:
        return "__ERROR__", str(e), 0
    stdout, stderr, rc = run_llvm_ir(llvm_ir, link_libs)
    return stdout.strip(), stderr.strip(), rc


def case_ok(expected: Expected, actual: Expected) -> bool:
    if expected[0] == "__ERROR__":
        return actual[0] == "__ERROR__" and expected[1] in actual[1]
    return actual == expected


def run_case(case: Case) -> tuple[str, Expected, Expected]:
    fname, source, expected = case
    return fname, expected, compile_and_run(source)


def worker_count() -> int:
    override = os.environ.get("NC_TEST_WORKERS")
    if override:
        try:
            count = int(override)
        except ValueError:
            raise RuntimeError("NC_TEST_WORKERS must be an integer")
        if count < 1:
            raise RuntimeError("NC_TEST_WORKERS must be >= 1")
        return count
    return max(1, min(32, os.cpu_count() or 1))


def run_all_cases(cases: list[Case]) -> list[tuple[str, Expected, Expected]]:
    workers = worker_count()
    if workers == 1:
        return [run_case(case) for case in cases]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run_case, cases))


def assert_cases(case_dir: str) -> None:
    for fname, expected, actual in run_all_cases(discover_cases(case_dir)):
        if expected[0] == "__ERROR__":
            assert actual[0] == "__ERROR__", f"{fname}: expected error, got {actual}"
            assert expected[1] in actual[1], f"{fname}: expected error containing {expected[1]!r}, got {actual[1]!r}"
        else:
            assert actual == expected, f"{fname}: expected '{expected}', got '{actual}'"


def main(case_dir: str) -> None:
    if len(sys.argv) > 1:
        fname = sys.argv[1]
        path = os.path.join(case_dir, fname) if not os.path.isabs(fname) else fname
        if not os.path.exists(path):
            print(f"File not found: {path}")
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            source = f.read()
        expected = parse_expected(source)
        print(f"=== {fname} ===")
        actual = compile_and_run(source)
        print(f"expected: {repr(expected)}")
        print(f"actual:   {repr(actual)}")
        print("PASS" if case_ok(expected, actual) else "FAIL")
    else:
        passed = 0
        failed = 0
        for fname, expected, actual in run_all_cases(discover_cases(case_dir)):
            ok = case_ok(expected, actual)
            if ok:
                print(f"  PASS  {fname}")
                passed += 1
            else:
                print(f"  FAIL  {fname}: expected {repr(expected)}, got {repr(actual)}")
                failed += 1
        print(f"\n{passed} passed, {failed} failed.")
        if failed:
            sys.exit(1)
