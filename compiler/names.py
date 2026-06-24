"""LLVM/runtime-safe symbol and ABI name helpers."""

import hashlib
import re


ABI_VERSION = "nc-abi-v1"


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


def abi_label(value: str, *, limit: int = 48) -> str:
    ident = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    if not ident:
        ident = "anon"
    if ident[0].isdigit():
        ident = f"_{ident}"
    return ident[:limit]


def abi_hash(signature: str, *, length: int = 10) -> str:
    digest = hashlib.sha256(f"{ABI_VERSION}\0{signature}".encode("utf-8")).hexdigest()
    return digest[:length]


def abi_symbol(kind: str, module_name: str, name: str, signature: str) -> str:
    """Return a readable internal ABI symbol with a stable collision hash."""
    readable = f"__nc_{kind}_{abi_label(module_name)}_{abi_label(name)}"
    return f"{readable}_{abi_hash(signature)}"


def module_object_label(module_name: str) -> str:
    return abi_label(module_name, limit=64)
