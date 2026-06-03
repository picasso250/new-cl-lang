"""Generic constraint helpers."""

from compiler.builtins import NUMERIC_TYPES


CMP_CONSTRAINT = "types.Cmp"
KNOWN_CONSTRAINTS = {"any", CMP_CONSTRAINT}


def satisfies_constraint(type_name: str, constraint: str) -> bool:
    if constraint == "any":
        return True
    if constraint == CMP_CONSTRAINT:
        return type_name in NUMERIC_TYPES
    return False
