"""Backend-neutral symbol name sanitizing."""

RESERVED_NAMES = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while",
}


def safe_ident(name: str) -> str:
    return (name.replace("*", "ptr_").replace("[]", "slice_")
            .replace(".", "_")
            .replace("?", "nullable_")
            .replace("[", "arr_").replace("]", "_")
            .replace("(", "_").replace(")", "_").replace(",", "_")
            .replace("->", "_to_"))


def safe_user_ident(name: str) -> str:
    ident = safe_ident(name)
    if ident in RESERVED_NAMES or ident.startswith("__nc_"):
        return f"nc_{ident}"
    return ident
