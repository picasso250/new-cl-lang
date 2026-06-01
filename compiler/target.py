"""Target selection for LLVM codegen and C/link steps."""

import os
import platform
from dataclasses import dataclass


@dataclass(frozen=True)
class TargetSpec:
    name: str
    triple: str
    object_ext: str
    exe_ext: str

    def resolve_link_lib(self, lib: str) -> str:
        if not lib:
            return lib
        if lib.startswith("-"):
            return lib
        lower = lib.lower()
        if any(sep in lib for sep in ("/", "\\")) or lower.endswith((".a", ".lib", ".o", ".obj")):
            return lib
        return f"-l{lib}"


WINDOWS_X64 = TargetSpec("windows-x64", "x86_64-w64-windows-gnu", ".obj", ".exe")
LINUX_X64 = TargetSpec("linux-x64", "x86_64-pc-linux-gnu", ".o", "")
TARGETS = {t.name: t for t in (WINDOWS_X64, LINUX_X64)}


def host_target_name() -> str:
    return "windows-x64" if platform.system().lower().startswith("win") else "linux-x64"


def get_target(name: str | None = None) -> TargetSpec:
    selected = name or os.environ.get("NC_TARGET") or host_target_name()
    try:
        return TARGETS[selected]
    except KeyError:
        known = ", ".join(sorted(TARGETS))
        raise RuntimeError(f"unsupported target '{selected}', expected one of: {known}")
