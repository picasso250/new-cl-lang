"""
NC 编译器 CLI。
用法:
  python nc.py run <file.nc>              # 编译 + 运行
  python nc.py run -c "<code>"            # 直接运行代码
  python nc.py compile <file.nc>          # 仅输出 C 代码
  python nc.py compile -c "<code>"        # 直接输出代码的 C 翻译
  python nc.py llvm-ir <file.nc>          # 实验：输出 LLVM IR
  python nc.py llvm-run <file.nc>         # 实验：JIT 运行 LLVM IR
"""
import sys
import os

from compiler import compile_nc_to_c, compile_nc_to_llvm_ir, run_c_code, run_llvm_code


def _read_source(args: list[str]) -> str:
    """从参数读取源码：-c "<code>" 或 <file.nc>。"""
    if not args:
        print("用法: 需提供文件路径或 -c '<代码>'")
        sys.exit(1)
    if args[0] == "-c":
        if len(args) < 2:
            print("用法: -c 后需跟代码字符串")
            sys.exit(1)
        return args[1]
    path = args[0]
    if not os.path.exists(path):
        print(f"文件不存在: {path}")
        sys.exit(1)
    return open(path, encoding="utf-8").read()


def cmd_run(args: list[str]):
    """编译并运行。"""
    source = _read_source(args)
    c_code = compile_nc_to_c(source)
    stdout, stderr, rc = run_c_code(c_code)
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    sys.exit(rc)


def cmd_compile(args: list[str]):
    """仅输出 C 代码。"""
    source = _read_source(args)
    c_code = compile_nc_to_c(source)
    print(c_code)


def cmd_llvm_ir(args: list[str]):
    """实验：仅输出 LLVM IR。"""
    source = _read_source(args)
    print(compile_nc_to_llvm_ir(source))


def cmd_llvm_run(args: list[str]):
    """实验：通过 llvmlite MCJIT 运行 LLVM IR。"""
    source = _read_source(args)
    ir_code = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_code(ir_code)
    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    sys.exit(rc)


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
    elif cmd == "llvm-ir":
        cmd_llvm_ir(rest)
    elif cmd == "llvm-run":
        cmd_llvm_run(rest)
    else:
        print(f"未知子命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
