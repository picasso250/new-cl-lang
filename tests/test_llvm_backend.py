import json
import os
import subprocess
import sys

import pytest

import compiler.llvm_codegen as llvm_codegen
from compiler import (
    build_llvm_ir, build_llvm_module_objects, compile_nc_sources_to_program_with_libs,
    compile_nc_sources_with_libs, compile_nc_to_llvm_ir, run_llvm_ir,
)


def test_llvm_smoke_empty_main():
    llvm_ir = compile_nc_to_llvm_ir("fun main() {}")
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout, stderr, rc) == ("", "", 0)


def test_empty_source_path_falls_back_to_memory():
    source = """import io
fun main() {
    io.println(__FILE__)
    io.println(__MODULE__)
}
"""
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([("", source)])
    stdout, stderr, rc = run_llvm_ir(llvm_ir, link_libs, support_c_sources)
    assert (stdout.strip(), stderr.strip(), rc) == ("<memory>\n<memory>", "", 0)


def test_llvm_os_args_and_env():
    source = """import io
import os
fun main() {
    let args = os.args()
    io.println(len(args))
    io.println(args[1])
    io.println(os.getenv("NC_OS_TEST_SET"))
    io.println(os.has_env("NC_OS_TEST_EMPTY"))
    io.println(os.getenv("NC_OS_TEST_EMPTY") == "")
    io.println(os.has_env("NC_OS_TEST_MISSING"))
}
"""
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([("<memory>", source)])
    stdout, stderr, rc = run_llvm_ir(
        llvm_ir,
        link_libs,
        support_c_sources,
        args=["alpha"],
        env={"NC_OS_TEST_SET": "value", "NC_OS_TEST_EMPTY": ""},
    )
    assert (stdout.strip(), stderr.strip(), rc) == ("2\nalpha\nvalue\n1\n1\n0", "", 0)


def test_llvm_file_io(tmp_path):
    path = str(tmp_path / "llvm_file_io.txt").replace("\\", "/")
    source = f"""import fs
import io
fun main() {{
    fs.write_file("{path}", "hello")!!
    let content = fs.read_file("{path}")!!
    io.println(content)
}}
"""
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([("<memory>", source)])
    stdout, stderr, rc = run_llvm_ir(llvm_ir, link_libs, support_c_sources)
    assert (stdout.strip(), stderr.strip(), rc) == ("hello", "", 0)


def test_llvm_fs_read_failure_try(tmp_path):
    path = str(tmp_path / "missing.txt").replace("\\", "/")
    source = f"""import fs
import io
fun main() {{
    try content = fs.read_file("{path}") {{
        io.println(content)
    }} else e {{
        io.println("fs.read_file failed")
    }}
}}
"""
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([("<memory>", source)])
    stdout, stderr, rc = run_llvm_ir(llvm_ir, link_libs, support_c_sources)
    assert (stdout.strip(), stderr.strip(), rc) == ("fs.read_file failed", "", 0)


def test_llvm_uses_external_ncrt_runtime():
    llvm_ir = compile_nc_to_llvm_ir("""import io
import runtime
fun main() {
    let m = map[str,str]{}
    m["a"] = "b"
    io.println(m["a"])
    runtime.gc_live()
}
""")

    assert 'define i8* @"__nc_gc_alloc"' not in llvm_ir
    assert 'declare i8* @"__nc_gc_alloc"' in llvm_ir
    assert "__nc_map_get" in llvm_ir


def test_extern_lib_path_is_collected_compile_only():
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([("<memory>", """
extern "some.lib" {
    fun helper(): i32
}
fun main() {}
""")])
    assert 'declare i32 @"helper"()' in llvm_ir
    assert link_libs == ["some.lib"]
    assert support_c_sources == []


def test_bare_extern_lib_name_is_collected():
    _llvm_ir, link_libs, _support_c_sources = compile_nc_sources_with_libs([("<memory>", """
extern "m" {
    fun fabs(x: f64): f64
}
fun main() {}
""")])
    assert link_libs == ["m"]


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="kernel32 is a Windows linker library")
def test_windows_bare_extern_links_kernel32():
    source = """import io
extern "kernel32" {
    fun GetCurrentProcessId(): i32
}
fun main() {
    let pid = GetCurrentProcessId()
    io.println(pid > 0)
}
"""
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([("<memory>", source)], target_name="windows-x64")
    stdout, stderr, rc = run_llvm_ir(llvm_ir, link_libs, support_c_sources, target_name="windows-x64")
    assert (stdout.strip(), stderr.strip(), rc) == ("1", "", 0)


def test_llvm_links_external_lib_path(tmp_path):
    helper_c = tmp_path / "helper.c"
    helper_obj = tmp_path / "helper.o"
    helper_lib = tmp_path / "helper.lib"
    helper_c.write_text("int nc_helper_add(int x) { return x + 35; }\n", encoding="utf-8")
    subprocess.run(["gcc", "-c", str(helper_c), "-o", str(helper_obj)], check=True)
    subprocess.run(["ar", "rcs", str(helper_lib), str(helper_obj)], check=True)
    lib_path = str(helper_lib).replace("\\", "/")
    source = f"""import io
extern "{lib_path}" {{
    fun nc_helper_add(x: i32): i32
}}
fun main() {{
    io.println(nc_helper_add(7))
}}
"""
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([("<memory>", source)])
    stdout, stderr, rc = run_llvm_ir(llvm_ir, link_libs, support_c_sources)
    assert link_libs == [lib_path]
    assert (stdout.strip(), stderr.strip(), rc) == ("42", "", 0)


def test_llvm_build_writes_ir_obj_and_exe(tmp_path):
    llvm_ir = compile_nc_to_llvm_ir("import io\nfun main() { io.println(42) }")
    ll_path, obj_path, exe_path = build_llvm_ir(llvm_ir, str(tmp_path), "main")
    assert os.path.exists(ll_path)
    assert os.path.exists(obj_path)
    ext = ".obj" if sys.platform.startswith("win") else ".o"
    assert os.path.exists(tmp_path / f"ncrt{ext}")
    assert not os.path.exists(tmp_path / "ncfs.obj")
    assert not os.path.exists(tmp_path / f"fs{ext}")
    assert os.path.exists(exe_path)
    result = subprocess.run([exe_path], capture_output=True, text=True)
    assert result.stdout.strip() == "42"
    assert result.returncode == 0


def test_llvm_build_uses_hosted_c_runtime_link_path(tmp_path, monkeypatch):
    commands = []

    def fake_run(cmd, capture_output, text):
        commands.append(cmd)

        class Result:
            returncode = 0
            stderr = ""

        return Result()

    monkeypatch.setattr(llvm_codegen, "object_from_llvm_ir", lambda llvm_ir, target_name=None: b"obj")
    monkeypatch.setattr(llvm_codegen, "build_ncrt_obj", lambda out_dir, target_name=None: os.path.join(out_dir, "ncrt.o"))
    monkeypatch.setattr(llvm_codegen, "build_support_c_objs", lambda out_dir, sources, target_name=None: [])
    monkeypatch.setattr(llvm_codegen.subprocess, "run", fake_run)

    _ll_path, _obj_path, exe_path = build_llvm_ir(
        "define i32 @main() { ret i32 0 }",
        str(tmp_path),
        "main",
        link_libs=["m"],
        target_name="linux-x64",
    )

    assert os.path.exists(exe_path) is False
    assert len(commands) == 1
    link_cmd = commands[0]
    assert link_cmd[0] == "gcc"
    assert "-nostdlib" not in link_cmd
    assert "-nodefaultlibs" not in link_cmd
    assert "-o" in link_cmd
    assert "-lm" in link_cmd
    hosted_args = llvm_codegen.get_target("linux-x64").hosted_runtime_link_args()
    if hosted_args:
        first_hosted = link_cmd.index(hosted_args[0])
        explicit = link_cmd.index("-lm")
        assert first_hosted < explicit


def test_llvm_build_links_fs_support_when_stdlib_fs_is_imported(tmp_path):
    data_path = str(tmp_path / "data.txt").replace("\\", "/")
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([
        ("<memory>", f'import fs\nfun main() {{ fs.write_file("{data_path}", "ok")!! }}')
    ])
    _ll_path, _obj_path, exe_path = build_llvm_ir(llvm_ir, str(tmp_path / "build"), "main", link_libs, support_c_sources)
    ext = ".obj" if sys.platform.startswith("win") else ".o"
    assert os.path.exists(tmp_path / "build" / f"ncrt{ext}")
    assert not os.path.exists(tmp_path / "build" / f"ncfs{ext}")
    assert os.path.exists(tmp_path / "build" / f"fs{ext}")
    result = subprocess.run([exe_path], capture_output=True, text=True)
    assert result.returncode == 0


def test_keep_objs_build_writes_module_objects_and_manifest(tmp_path):
    root = tmp_path / "project"
    app = root / "app"
    calc = root / "calc"
    app.mkdir(parents=True)
    calc.mkdir()
    (app / "main.nc").write_text(
        "import io\nimport calc\nfun main() { io.println(calc.add(20, 22)) }\n",
        encoding="utf-8",
    )
    (calc / "calc.nc").write_text(
        "fun add(a: i32, b: i32): i32 { a + b }\n",
        encoding="utf-8",
    )
    sources = [(str(app / "main.nc"), (app / "main.nc").read_text(encoding="utf-8"))]
    program, link_libs, support_c_sources, module_names = compile_nc_sources_to_program_with_libs(sources)
    manifest_path, obj_paths, _ncrt_obj, exe_path = build_llvm_module_objects(
        program,
        module_names,
        str(tmp_path / "build"),
        "main",
        link_libs,
        support_c_sources,
        keep_objs=True,
    )
    assert {os.path.basename(path) for path in obj_paths} == {
        f"app{'.obj' if sys.platform.startswith('win') else '.o'}",
        f"calc{'.obj' if sys.platform.startswith('win') else '.o'}",
    }
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
    assert manifest["abi_version"] == "nc-abi-v1"
    assert len(manifest["modules"]) == 2
    calc_node = next(node for node in manifest["dependency_graph"] if node["name"] == "calc")
    app_node = next(node for node in manifest["dependency_graph"] if node["name"] == "app")
    assert calc_node["exports"][0]["symbol"].startswith("__nc_F_calc_calc_add_")
    assert {"kind": "function", "name": "calc.add", "module": "calc"} in app_node["requires"]
    result = subprocess.run([exe_path], capture_output=True, text=True)
    assert result.stdout.strip() == "42"
    assert result.returncode == 0


def test_keep_objs_keeps_stdlib_c_support_separate(tmp_path):
    data_path = str(tmp_path / "data.txt").replace("\\", "/")
    source = f'import fs\nfun main() {{ fs.write_file("{data_path}", "ok")!! }}'
    program, link_libs, support_c_sources, module_names = compile_nc_sources_to_program_with_libs([("<memory>", source)])
    manifest_path, _obj_paths, _ncrt_obj, exe_path = build_llvm_module_objects(
        program,
        module_names,
        str(tmp_path / "build"),
        "main",
        link_libs,
        support_c_sources,
        keep_objs=True,
    )
    ext = ".obj" if sys.platform.startswith("win") else ".o"
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
    assert os.path.exists(tmp_path / "build" / f"fs{ext}")
    assert str(tmp_path / "build" / f"fs{ext}") in manifest["support_objects"]
    result = subprocess.run([exe_path], capture_output=True, text=True)
    assert result.returncode == 0


def test_stdlib_support_c_sources_are_collected_once():
    _llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([
        ("<memory>", """
import fs
import fs
fun main() {
    let x = fs.exists("nope")
}
""")
    ])
    assert link_libs == []
    assert len(support_c_sources) == 1
    assert support_c_sources[0].replace("\\", "/").endswith("/stdlib/fs/fs.c")


def test_linux_module_rejected_on_windows_target():
    with pytest.raises(RuntimeError, match="module 'linux' is only available"):
        compile_nc_sources_with_libs([("<memory>", "import linux\nfun main() {}")], target_name="windows-x64")


def test_linux_target_emits_linux_triple():
    llvm_ir = compile_nc_sources_with_libs([("<memory>", "fun main() {}")], target_name="linux-x64")[0]
    assert 'target triple = "x86_64-pc-linux-gnu"' in llvm_ir


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="linux stdlib runs only on Linux")
def test_linux_stdlib_syscalls():
    source = """import linux
fun main() {
    let pid = linux.getpid()
    if pid <= 0 {
        err "bad pid"
    }
    let n = linux.write_str(1, "A\\n")
}
"""
    llvm_ir, link_libs, support_c_sources = compile_nc_sources_with_libs([("<memory>", source)], target_name="linux-x64")
    stdout, stderr, rc = run_llvm_ir(llvm_ir, link_libs, support_c_sources, target_name="linux-x64")
    assert (stdout.strip(), stderr.strip(), rc) == ("A", "", 0)
