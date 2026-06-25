"""
NC 编译器 CLI。
用法:
  python nc.py run <file.nc>              # 编译 + 运行
  python nc.py run <dir>                  # 编译并运行目录内所有 .nc
  python nc.py run -c "<code>"            # 直接运行代码
  python nc.py compile <file.nc>
  python nc.py compile <dir>
  python nc.py compile -c "<code>"
  python nc.py build <file.nc|dir>
"""
import sys
import os

from compiler import (
    build_llvm_ir, build_llvm_module_objects, compile_nc_sources_to_llvm_ir,
    compile_nc_sources_to_program_with_libs, compile_nc_sources_with_libs, run_llvm_ir,
)
from compiler.target import get_target


def _parse_target(args: list[str]) -> tuple[str, list[str]]:
    rest = []
    target = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--target":
            if i + 1 >= len(args):
                print("用法: --target 后需跟 windows-x64 或 linux-x64", file=sys.stderr)
                sys.exit(1)
            target = args[i + 1]
            i += 2
            continue
        if arg.startswith("--target="):
            target = arg.split("=", 1)[1]
            i += 1
            continue
        rest.append(arg)
        i += 1
    try:
        return get_target(target).name, rest
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _parse_keep_objs(args: list[str]) -> tuple[bool, list[str]]:
    rest = []
    keep_objs = False
    for arg in args:
        if arg == "--keep-objs":
            keep_objs = True
            continue
        rest.append(arg)
    return keep_objs, rest


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
    target_name, args = _parse_target(args)
    sources = _read_sources(args)
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs(sources, target_name=target_name)
    stdout, stderr, rc = run_llvm_ir(llvm_ir, link_libs, support_c_sources, target_name=target_name)
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    sys.exit(rc)


def cmd_compile(args: list[str]):
    """仅输出后端代码。"""
    target_name, args = _parse_target(args)
    sources = _read_sources(args)
    print(compile_nc_sources_to_llvm_ir(sources, target_name=target_name))


def cmd_build(args: list[str]):
    """生成 build/main.* 和 build/main.exe。"""
    target_name, args = _parse_target(args)
    keep_objs, args = _parse_keep_objs(args)
    sources = _read_sources(args)
    if keep_objs:
        program, link_libs, support_c_sources, module_names = compile_nc_sources_to_program_with_libs(sources, target_name=target_name)
        manifest_path, obj_paths, _ncrt_objs, exe_path = build_llvm_module_objects(
            program,
            module_names,
            "build",
            "main",
            link_libs,
            support_c_sources,
            target_name=target_name,
            keep_objs=True,
        )
        print(manifest_path)
        for obj_path in obj_paths:
            print(obj_path)
        print(exe_path)
        return
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs(sources, target_name=target_name)
    ll_path, obj_path, _ncrt, exe_path = build_llvm_ir(llvm_ir, "build", "main", link_libs, support_c_sources, target_name=target_name)
    print(ll_path)
    print(obj_path)
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
