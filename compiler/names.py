"""LLVM/runtime-safe symbol name sanitizing."""


def safe_ident(name: str) -> str:
    return (name.replace("*", "ptr_").replace("[]", "slice_")
            .replace(".", "_")
            .replace("?", "nullable_")
            .replace("[", "arr_").replace("]", "_")
            .replace("(", "_").replace(")", "_").replace(",", "_")
            .replace("->", "_to_"))


def safe_user_ident(name: str) -> str:
    ident = safe_ident(name)
    if ident.startswith("__nc_"):
        return f"nc_{ident}"
    return ident
