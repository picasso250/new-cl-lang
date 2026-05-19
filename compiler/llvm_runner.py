"""Experimental llvmlite MCJIT runner for NC LLVM IR."""

import ctypes

import llvmlite
from llvmlite import binding as llvm


_llvm_initialized = False
_registered_callbacks = []


def _ensure_llvm():
    global _llvm_initialized
    if not _llvm_initialized:
        version = [int(p) for p in llvmlite.__version__.split(".")[:2]]
        if version < [0, 45]:
            llvm.initialize()
        llvm.initialize_native_target()
        llvm.initialize_native_asmprinter()
        _llvm_initialized = True


def run_llvm_code(ir_text: str) -> "tuple[str, str, int]":
    """LLVM IR -> JIT run main -> (stdout, stderr, returncode)."""
    _ensure_llvm()
    output: list[str] = []

    callback_ty = ctypes.CFUNCTYPE(None, ctypes.c_int32)

    @callback_ty
    def print_i32(value):
        output.append(str(value))

    _registered_callbacks.append(print_i32)
    llvm.add_symbol("__nc_print_i32", ctypes.cast(print_i32, ctypes.c_void_p).value)

    llvm_module = llvm.parse_assembly(ir_text)
    llvm_module.verify()

    target = llvm.Target.from_default_triple()
    target_machine = target.create_target_machine()
    backing_mod = llvm.parse_assembly("")
    engine = llvm.create_mcjit_compiler(backing_mod, target_machine)
    engine.add_module(llvm_module)
    engine.finalize_object()
    engine.run_static_constructors()

    main_ptr = engine.get_function_address("main")
    if main_ptr == 0:
        return "", "main not found", 1
    main_fn = ctypes.CFUNCTYPE(ctypes.c_int32)(main_ptr)
    rc = int(main_fn())
    stdout = "\n".join(output)
    if stdout:
        stdout += "\n"
    return stdout, "", rc
