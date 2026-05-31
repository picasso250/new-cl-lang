"""
Language core case suite.

Usage:
  python tests/test_language_cases.py
  python tests/test_language_cases.py case_033_method.nc
"""
import os

from case_runner import assert_cases, main


CASE_DIR = os.path.join(os.path.dirname(__file__), "..", "test_cases")


def test_language_cases():
    assert_cases(CASE_DIR)


if __name__ == "__main__":
    main(CASE_DIR)
