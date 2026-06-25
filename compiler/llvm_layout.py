from llvmlite import ir

from compiler.type_ref import (
    ArrayTypeRef,
    FunctionType,
    PointerType,
    SliceType,
    as_map_type,
    format_type_ref,
    parse_array_type,
    parse_fn_type,
    parse_map_type,
    parse_slice_type,
    parse_type_ref,
    type_key,
)


INT_TYPES = {
    "i8": ir.IntType(8),
    "i16": ir.IntType(16),
    "i32": ir.IntType(32),
    "i64": ir.IntType(64),
    "u8": ir.IntType(8),
    "u16": ir.IntType(16),
    "u32": ir.IntType(32),
    "u64": ir.IntType(64),
    "bool": ir.IntType(1),
    "rune": ir.IntType(32),
}
SIGNED_INT_TYPES = {"i8", "i16", "i32", "i64"}
UNSIGNED_INT_TYPES = {"u8", "u16", "u32", "u64", "bool", "rune"}
FLOAT_TYPES = {"f32": ir.FloatType(), "f64": ir.DoubleType()}
I8PTR = ir.IntType(8).as_pointer()
STR_TYPE = ir.LiteralStructType([I8PTR, ir.IntType(64)])
ERROR_FRAME_TYPE = ir.LiteralStructType([STR_TYPE, STR_TYPE, ir.IntType(32), ir.IntType(32)])
MAP_HASH_FN_TYPE = ir.FunctionType(ir.IntType(64), [I8PTR])
MAP_EQ_FN_TYPE = ir.FunctionType(ir.IntType(32), [I8PTR, I8PTR])
MAP_DESC_TYPE = ir.LiteralStructType([
    ir.IntType(64), ir.IntType(64), ir.IntType(64), ir.IntType(64),
    ir.IntType(64), ir.IntType(64),
    MAP_HASH_FN_TYPE.as_pointer(), MAP_EQ_FN_TYPE.as_pointer(),
])
MAP_DESC_PTR = MAP_DESC_TYPE.as_pointer()
MAP_TYPE = ir.LiteralStructType([MAP_DESC_PTR, I8PTR, ir.IntType(64), ir.IntType(64), ir.IntType(64)])
RAW_SLICE_TYPE = ir.LiteralStructType([I8PTR, ir.IntType(64), ir.IntType(64)])
ERROR_TYPE = ir.LiteralStructType([STR_TYPE, RAW_SLICE_TYPE])
STRUCT_TYPES: dict[str, ir.Type] = {}
STRUCT_FIELDS: dict[str, list[tuple[str, str]]] = {}
STRUCT_FIELD_INDEX: dict[str, dict[str, int]] = {}
STRUCT_EMBEDS: dict[str, dict[str, str]] = {}
ENUM_VARIANTS: dict[str, dict[str, int]] = {}
IFACE_METHODS: dict[str, list[tuple[str, list[str], str]]] = {}
IFACE_TYPES: dict[str, ir.LiteralStructType] = {}


def llvm_type(nc_type: str | None):
    nc_type = nc_type or "void"
    ref = parse_type_ref(nc_type)
    nc_key = type_key(ref)
    if nc_type == "void":
        return ir.VoidType()
    if nc_type in INT_TYPES:
        return INT_TYPES[nc_type]
    if nc_type in FLOAT_TYPES:
        return FLOAT_TYPES[nc_type]
    if nc_type == "str":
        return STR_TYPE
    if nc_type == "error":
        return ERROR_TYPE
    if nc_type == "nc_map" or as_map_type(ref) is not None:
        return MAP_TYPE
    if nc_type in IFACE_METHODS:
        if nc_type not in IFACE_TYPES:
            IFACE_TYPES[nc_type] = ir.LiteralStructType([I8PTR, I8PTR])
        return IFACE_TYPES[nc_type]
    if nc_type in ("*void", "?*void"):
        return I8PTR
    if isinstance(ref, FunctionType):
        arg_types, ret_type = list(ref.params), ref.ret
        call_type = ir.FunctionType(
            llvm_type(ret_type),
            [I8PTR] + [llvm_type(arg_type) for arg_type in arg_types],
        ).as_pointer()
        return ir.LiteralStructType([call_type, I8PTR])
    if isinstance(ref, PointerType):
        return llvm_type(ref.inner).as_pointer()
    if nc_type in ENUM_VARIANTS:
        return ir.IntType(32)
    if nc_type in STRUCT_TYPES:
        return STRUCT_TYPES[nc_type]
    if isinstance(ref, SliceType):
        elem_type = ref.elem
        return ir.LiteralStructType([
            llvm_type(elem_type).as_pointer(),
            ir.IntType(64),
            ir.IntType(64),
        ])
    if isinstance(ref, ArrayTypeRef):
        length, elem_type = ref.length, ref.elem
        return llvm_type(elem_type).as_pointer()
    raise NotImplementedError(f"LLVM backend does not support type: {nc_type}")


class LLVMLayout:
    def sizeof_type(self, nc_type: str) -> int:
        ref = parse_type_ref(nc_type)
        nc_key = type_key(ref)
        if nc_type == "void":
            raise NotImplementedError("LLVM backend cannot sizeof void")
        if nc_type in ("i8", "u8", "bool"):
            return 1
        if nc_type in ("i16", "u16"):
            return 2
        if nc_type in ("i32", "u32", "f32", "rune") or nc_type in ENUM_VARIANTS:
            return 4
        if nc_type in ("i64", "u64", "f64"):
            return 8
        if nc_type == "str":
            return 16
        if nc_type == "error":
            return 40
        if nc_type == "nc_map" or as_map_type(ref) is not None:
            return 40
        if isinstance(ref, PointerType):
            return 8
        if isinstance(ref, FunctionType):
            return 16
        if nc_type in IFACE_METHODS:
            return 16
        if isinstance(ref, SliceType):
            return 24
        if isinstance(ref, ArrayTypeRef):
            return 8
        if nc_type in STRUCT_FIELDS:
            return self.sizeof_fields([field_type for _field_name, field_type in STRUCT_FIELDS[nc_type]])
        raise NotImplementedError(f"LLVM backend cannot sizeof {nc_type}")

    def alignof_type(self, nc_type: str) -> int:
        ref = parse_type_ref(nc_type)
        if nc_type == "void":
            raise NotImplementedError("LLVM backend cannot alignof void")
        if nc_type in ("i8", "u8", "bool"):
            return 1
        if nc_type in ("i16", "u16"):
            return 2
        if nc_type in ("i32", "u32", "f32", "rune") or nc_type in ENUM_VARIANTS:
            return 4
        if nc_type in ("i64", "u64", "f64", "str", "error", "nc_map") or as_map_type(ref) is not None:
            return 8
        if isinstance(ref, PointerType):
            return 8
        if isinstance(ref, FunctionType) or nc_type in IFACE_METHODS:
            return 8
        if isinstance(ref, SliceType):
            return 8
        if isinstance(ref, ArrayTypeRef):
            return 8
        if nc_type in STRUCT_FIELDS:
            aligns = [self.alignof_type(field_type) for _field_name, field_type in STRUCT_FIELDS[nc_type]]
            return max(aligns, default=1)
        raise NotImplementedError(f"LLVM backend cannot alignof {nc_type}")

    def align_to(self, value: int, alignment: int) -> int:
        return ((value + alignment - 1) // alignment) * alignment

    def aligned_sizeof_type(self, nc_type: str) -> int:
        return self.align_to(self.sizeof_type(nc_type), self.alignof_type(nc_type))

    def sizeof_fields(self, field_types: list[str]) -> int:
        offset = 0
        max_align = 1
        for field_type in field_types:
            align = self.alignof_type(field_type)
            max_align = max(max_align, align)
            offset = self.align_to(offset, align)
            offset += self.sizeof_type(field_type)
        return self.align_to(offset, max_align)
