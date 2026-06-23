"""Generic constraint helpers."""

EQ_CONSTRAINT = "types.Eq"
ORD_CONSTRAINT = "types.Ord"
HASH_CONSTRAINT = "types.Hash"
ZERO_CONSTRAINT = "types.Zero"
KNOWN_CONSTRAINTS = {"any", EQ_CONSTRAINT, ORD_CONSTRAINT, HASH_CONSTRAINT, ZERO_CONSTRAINT}


def satisfies_constraint(type_name: str, constraint: str) -> bool:
    if constraint == "any":
        return True
    # Composite and named user types require the symbol table, so typecheck
    # performs the authoritative recursive check after monomorphization.
    if constraint in {ORD_CONSTRAINT, EQ_CONSTRAINT, HASH_CONSTRAINT, ZERO_CONSTRAINT}:
        return True
    return False
