"""
Standard library and language builtin case suite.

Usage:
  python tests/test_stdlib.py
  python tests/test_stdlib.py case_245_strings_queries.nc
"""
import os

from case_runner import assert_cases, main


CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "stdlib_cases")


def test_stdlib_cases():
    assert_cases(CASE_DIR)


if __name__ == "__main__":
    main(CASE_DIR)
