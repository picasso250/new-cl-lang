"""C ABI naming and type mapping for generated code."""

NC_TO_C = {
    "i8": "int8_t",
    "i16": "int16_t",
    "i32": "int",
    "i64": "long long",
    "u8": "uint8_t",
    "u16": "uint16_t",
    "u32": "unsigned int",
    "u64": "unsigned long long",
    "f32": "float",
    "f64": "double",
    "bool": "int",
    "void": "void",
    "str": "str",
}

C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while",
}


def type_to_c(nc_type: str) -> str:
    if nc_type.startswith("fn("):
        return fn_type_name(nc_type)
    if nc_type.startswith("[]"):
        return slice_type_name(nc_type[2:])
    if nc_type.startswith("?*"):
        return type_to_c(nc_type[2:]) + "*"
    if nc_type.startswith("*"):
        return type_to_c(nc_type[1:]) + "*"
    return NC_TO_C.get(nc_type, nc_type)


def c_ident(name: str) -> str:
    return (name.replace("*", "ptr_").replace("[]", "slice_")
            .replace("?", "nullable_")
            .replace("[", "arr_").replace("]", "_")
            .replace("(", "_").replace(")", "_").replace(",", "_")
            .replace("->", "_to_"))


def c_user_ident(name: str) -> str:
    ident = c_ident(name)
    if ident in C_KEYWORDS or ident.startswith("__nc_"):
        return f"nc_{ident}"
    return ident


def fn_type_name(nc_type: str) -> str:
    return f"nc_{c_ident(nc_type)}"


def slice_type_name(elem_type: str) -> str:
    return f"nc_slice_{c_ident(elem_type)}"


def slice_append_name(elem_type: str) -> str:
    return f"__nc_append_{c_ident(elem_type)}"


def slice_copy_name(elem_type: str) -> str:
    return f"__nc_slice_copy_{c_ident(elem_type)}"
