"""LLVM backend regression over positive single-file cases."""

import os
import re
from pathlib import Path

from compiler import compile_nc_sources_to_llvm_ir, run_llvm_ir


ROOT = Path(__file__).resolve().parent.parent
CASE_DIR = ROOT / "test_cases"
DEFERRED_TOKENS = ()


def expected_stdout(path: Path) -> str | None:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*# STDOUT:\s?(.*)$", line)
        if match:
            lines.append(match.group(1))
    if not lines:
        return None
    return "\n".join(lines)


def expected_run(path: Path) -> tuple[str, str, int] | None:
    stdout = []
    stderr = []
    rc = 0
    found = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stdout_match = re.match(r"\s*# STDOUT:\s?(.*)$", line)
        if stdout_match:
            stdout.append(stdout_match.group(1))
            found = True
        stderr_match = re.match(r"\s*# STDERR:\s?(.*)$", line)
        if stderr_match:
            stderr.append(stderr_match.group(1))
            found = True
        rc_match = re.match(r"\s*# RC:\s?(-?\d+)\s*$", line)
        if rc_match:
            rc = int(rc_match.group(1))
            found = True
    if not found:
        return None
    return "\n".join(stdout), "\n".join(stderr), rc


def expected_error(path: Path) -> str | None:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*# ERROR:\s?(.*)$", line)
        if match:
            lines.append(match.group(1))
    if not lines:
        return None
    return "\n".join(lines)


def llvm_positive_cases():
    cases = []
    for path in sorted(CASE_DIR.glob("case_*.nc")):
        text = path.read_text(encoding="utf-8")
        expected = expected_run(path)
        if expected is None:
            continue
        if any(token in text for token in DEFERRED_TOKENS):
            continue
        cases.append((path, expected))
    return cases


def llvm_error_cases():
    cases = []
    for path in sorted(CASE_DIR.glob("case_*.nc")):
        expected = expected_error(path)
        if expected is not None:
            cases.append((path, expected))
    return cases


def test_llvm_positive_single_file_cases():
    failures = []
    for path, expected in llvm_positive_cases():
        try:
            source = path.read_text(encoding="utf-8")
            llvm_ir = compile_nc_sources_to_llvm_ir([(str(path), source)])
            stdout, stderr, rc = run_llvm_ir(llvm_ir)
        except Exception as exc:
            failures.append(
                f"{os.path.relpath(path, ROOT)}: raised={type(exc).__name__}: {exc}"
            )
            continue
        actual = (stdout.strip(), stderr.strip(), rc)
        if actual != expected:
            failures.append(
                f"{os.path.relpath(path, ROOT)}: actual={actual!r}, "
                f"expected={expected!r}, tail_stderr={stderr[-500:]!r}"
            )
    assert not failures, "\n".join(failures)


def test_llvm_error_single_file_cases():
    failures = []
    for path, expected in llvm_error_cases():
        try:
            source = path.read_text(encoding="utf-8")
            compile_nc_sources_to_llvm_ir([(str(path), source)])
        except Exception as exc:
            diagnostic = str(exc)
            if expected not in diagnostic:
                failures.append(
                    f"{os.path.relpath(path, ROOT)}: expected error containing={expected!r}, "
                    f"diagnostic={diagnostic[-500:]!r}"
                )
        else:
            failures.append(
                f"{os.path.relpath(path, ROOT)}: expected error containing={expected!r}, "
                "but compile succeeded"
            )
    assert not failures, "\n".join(failures)
