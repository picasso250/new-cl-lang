"""
NC 编译器 CLI。
用法:
  python nc.py run <file.nc>              # 编译 + 运行
  python nc.py run <dir>                  # 编译并运行目录内所有 .nc
  python nc.py run -c "<code>"            # 直接运行代码
  python nc.py compile [--backend c|llvm] <file.nc>
  python nc.py compile [--backend c|llvm] <dir>
  python nc.py compile [--backend c|llvm] -c "<code>"
  python nc.py build [--backend c|llvm] <file.nc|dir>
"""
import sys
import os

from compiler import (
    build_c_code, build_llvm_ir, compile_nc_sources_to_c,
    compile_nc_sources_to_llvm_ir, run_c_code, run_llvm_ir,
)


def _parse_backend(args: list[str]) -> tuple[str, list[str]]:
    """Parse --backend c|llvm. LLVM is the default backend."""
    backend = "llvm"
    rest = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--backend":
            if i + 1 >= len(args):
                print("用法: --backend 后需跟 c 或 llvm")
                sys.exit(1)
            backend = args[i + 1]
            i += 2
            continue
        if arg.startswith("--backend="):
            backend = arg.split("=", 1)[1]
            i += 1
            continue
        rest.append(arg)
        i += 1
    if backend not in ("c", "llvm"):
        print(f"未知 backend: {backend}")
        sys.exit(1)
    return backend, rest


def _read_sources(args: list[str]) -> list[tuple[str, str]]:
    """从参数读取源码：-c "<code>"、<file.nc> 或 <dir>。"""
    if not args:
        print("用法: 需提供文件路径或 -c '<代码>'")
        sys.exit(1)
    if args[0] == "-c":
        if len(args) < 2:
            print("用法: -c 后需跟代码字符串")
            sys.exit(1)
        return [("<command>", args[1])]
    path = args[0]
    if not os.path.exists(path):
        print(f"文件不存在: {path}")
        sys.exit(1)
    if os.path.isdir(path):
        files = [
            os.path.join(path, name)
            for name in sorted(os.listdir(path))
            if name.endswith(".nc")
        ]
        if not files:
            print(f"目录中没有 .nc 文件: {path}")
            sys.exit(1)
        return [(file, open(file, encoding="utf-8").read()) for file in files]
    return [(path, open(path, encoding="utf-8").read())]


def cmd_run(args: list[str]):
    """编译并运行。"""
    backend, args = _parse_backend(args)
    sources = _read_sources(args)
    if backend == "llvm":
        llvm_ir = compile_nc_sources_to_llvm_ir(sources)
        stdout, stderr, rc = run_llvm_ir(llvm_ir)
    else:
        c_code = compile_nc_sources_to_c(sources)
        stdout, stderr, rc = run_c_code(c_code)
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    sys.exit(rc)


def cmd_compile(args: list[str]):
    """仅输出后端代码。"""
    backend, args = _parse_backend(args)
    sources = _read_sources(args)
    if backend == "llvm":
        print(compile_nc_sources_to_llvm_ir(sources))
    else:
        print(compile_nc_sources_to_c(sources))


def cmd_build(args: list[str]):
    """生成 build/main.* 和 build/main.exe。"""
    backend, args = _parse_backend(args)
    sources = _read_sources(args)
    if backend == "llvm":
        llvm_ir = compile_nc_sources_to_llvm_ir(sources)
        ll_path, obj_path, exe_path = build_llvm_ir(llvm_ir, "build", "main")
        print(ll_path)
        print(obj_path)
        print(exe_path)
    else:
        c_code = compile_nc_sources_to_c(sources)
        c_path, exe_path = build_c_code(c_code, "build", "main")
        print(c_path)
        print(exe_path)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    if cmd == "run":
        cmd_run(rest)
    elif cmd == "compile":
        cmd_compile(rest)
    elif cmd == "build":
        cmd_build(rest)
    else:
        print(f"未知子命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
