"""C ABI naming and type mapping for generated code."""

NC_TO_C = {
    "i32": "int",
    "i64": "long long",
    "u32": "unsigned int",
    "u64": "unsigned long long",
    "f32": "float",
    "f64": "double",
    "bool": "int",
    "void": "void",
    "str": "str",
}


def type_to_c(nc_type: str) -> str:
    if nc_type.startswith("[]"):
        return slice_type_name(nc_type[2:])
    if nc_type.startswith("*"):
        return type_to_c(nc_type[1:]) + "*"
    return NC_TO_C.get(nc_type, nc_type)


def c_ident(name: str) -> str:
    return name.replace("*", "ptr_").replace("[]", "slice_").replace("[", "arr_").replace("]", "_")


def slice_type_name(elem_type: str) -> str:
    return f"nc_slice_{c_ident(elem_type)}"


def slice_append_name(elem_type: str) -> str:
    return f"__nc_append_{c_ident(elem_type)}"


def slice_copy_name(elem_type: str) -> str:
    return f"__nc_slice_copy_{c_ident(elem_type)}"
