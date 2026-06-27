"""Type erasure for generic functions — replaces deep-copy monomorphization.

For each generic function instantiation, generates:
1. An erased function declaration (with desc + raw params, empty body)
2. At call sites: descriptor constant + slot setup

The actual LLVM IR body is emitted by LLVMCodegen when it sees the
`_erased_template` metadata on the erased function.
"""

from __future__ import annotations

from compiler.ast import (
    Block,
    FunctionCall,
    FunctionDeclaration,
    Identifier,
    Param,
    Return,
    StructDecl,
    StructLiteral,
)
from compiler.type_ref import format_type_ref, NamedType, PointerType


# Sentinel type name for erased T values (compiler-internal).
RAW_TYPE = "raw"

# Descriptor struct field names
DESC_SIZE_FIELD = "size"


def _desc_struct_name(base_name: str) -> str:
    return f"__desc_{base_name}"


def _erased_func_name(base_name: str) -> str:
    return f"__erased_{base_name}"


def make_descriptor_struct(base_name: str, ops: set[str]) -> StructDecl:
    """Generate a synthetic StructDecl for the descriptor.

    For Stage 1, only the 'size' field is emitted as i32.
    Function pointer fields (lt, eq, hash, zero) will be added in later stages.
    """
    fields: list[tuple[str, str]] = []

    if "size" in ops:
        fields.append((DESC_SIZE_FIELD, "i32"))

    # TODO Stage 2+: add lt/eq/hash/zero as function pointer fields

    return StructDecl(
        name=_desc_struct_name(base_name),
        fields=fields,
    )


def collect_ops_for_func(fn: FunctionDeclaration) -> set[str]:
    """Deduce which descriptor operations are needed from the function signature.

    For Stage 1, this is signature-based only (body analysis comes later).
    """
    ops: set[str] = set()
    type_param_names = set(fn.type_params or [])

    for param in fn.params:
        if param.type in type_param_names:
            ops.add("size")

    if fn.return_type in type_param_names:
        ops.add("size")

    if not ops:
        ops.add("size")

    return ops


def erase_function(fn: FunctionDeclaration, ops: set[str]) -> FunctionDeclaration:
    """Generate the erased version of a generic function.

    The erased function at the AST level:
    - Original T params become raw
    - Return type becomes raw (if it was T), void otherwise
    - No desc parameter at AST level (LLVM codegen adds it)
    - Body is empty (LLVM codegen fills it from _erased_template metadata)
    """
    erased_name = _erased_func_name(fn.name)

    params = []
    for param in fn.params:
        if param.type in (fn.type_params or []):
            params.append(Param(param.name, RAW_TYPE, default=param.default))
        else:
            params.append(param)

    return_type = RAW_TYPE if fn.return_type in (fn.type_params or []) else fn.return_type

    erased = FunctionDeclaration(
        name=erased_name,
        params=params,
        return_type=return_type,
        body=Block([Return(Identifier(fn.params[0].name))]) if fn.params and return_type == RAW_TYPE else Block([]),
    )
    # Attach metadata so LLVM codegen can regenerate the body
    erased._erased_template = fn
    erased._erased_ops = ops
    erased._is_erased_generic = True

    return erased


def erase_call_site(
    call: FunctionCall,
    fn: FunctionDeclaration,
    ops: set[str],
    type_args: list[str],
) -> FunctionCall:
    """Rewrite a call site to use the erased function.

    Returns the rewritten FunctionCall. The caller is responsible for
    also generating the descriptor constant (handled in LLVM codegen).

    The call is rewritten to:
    - Add desc pointer as first arg
    - Add ret slot pointer if T return
    - Original args stay as-is (LLVM codegen bitcasts them)
    """
    erased_name = _erased_func_name(fn.name)

    new_args = []

    # Add desc pointer (resolved in LLVM codegen by name)
    new_args.append(Identifier(f"__desc_{fn.name}_{'_'.join(type_args)}"))

    # Add ret slot if T return
    if fn.return_type in (fn.type_params or []):
        new_args.append(Identifier(f"__ret_{fn.name}_{'_'.join(type_args)}"))

    new_args.extend(call.args)

    rewritten = FunctionCall(
        name=erased_name,
        args=new_args,
        type_args=[],
    )
    rewritten._erased_call = True
    rewritten._erased_type_args = type_args
    rewritten._erased_template_name = fn.name

    return rewritten
