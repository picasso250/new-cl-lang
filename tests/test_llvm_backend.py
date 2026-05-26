import os
import subprocess

from compiler import build_llvm_ir, compile_nc_to_llvm_ir, run_llvm_ir


def test_llvm_smoke_empty_main():
    llvm_ir = compile_nc_to_llvm_ir("fun main() {}")
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout, stderr, rc) == ("", "", 0)


def test_llvm_println_and_control_flow():
    source = """import io
fun add(x: i32, y: i32): i32 { return x + y }
fun main() {
    let x: i32 = add(1, 2)
    if x == 3 { io.println(x) } else { io.println(0) }
    let y: i32 = 0
    for y < 2 { y = y + 1 }
    io.println(y)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("3\n2", "", 0)


def test_llvm_build_writes_ir_obj_and_exe(tmp_path):
    llvm_ir = compile_nc_to_llvm_ir("import io\nfun main() { io.println(42) }")
    ll_path, obj_path, exe_path = build_llvm_ir(llvm_ir, str(tmp_path), "main")
    assert os.path.exists(ll_path)
    assert os.path.exists(obj_path)
    assert os.path.exists(exe_path)
    result = subprocess.run([exe_path], capture_output=True, text=True)
    assert result.stdout.strip() == "42"
    assert result.returncode == 0
