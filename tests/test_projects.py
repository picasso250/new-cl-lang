"""项目级测试：目录即同模块，多文件自动互见。"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run_nc(*args, cwd=ROOT):
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "nc.py"), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_multifile_function_run():
    result = run_nc("run", os.path.join("test_cases", "project_095_multifile"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "5"


def test_multifile_struct_run():
    result = run_nc("run", os.path.join("test_cases", "project_096_multifile_struct"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "7"


def test_multifile_inferred_return_run():
    result = run_nc("run", os.path.join("test_cases", "project_120_multifile_infer_return"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "11"


def test_default_build_outputs_llvm_ir_obj_and_exe():
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(ROOT, "test_cases", "project_095_multifile")
        build = run_nc("build", project, cwd=tmp)
        assert build.returncode == 0, build.stderr
        ll_path = os.path.join(tmp, "build", "main.ll")
        obj_path = os.path.join(tmp, "build", "main.obj")
        ncrt_obj_path = os.path.join(tmp, "build", "ncrt.obj")
        exe_path = os.path.join(tmp, "build", "main.exe")
        assert os.path.exists(ll_path)
        assert os.path.exists(obj_path)
        assert os.path.exists(ncrt_obj_path)
        assert os.path.exists(exe_path)
        result = subprocess.run([exe_path], capture_output=True, text=True)
        assert result.stdout.strip() == "5"
        assert result.returncode == 0


def test_multifile_diagnostic_uses_source_file():
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "app")
        os.mkdir(project)
        with open(os.path.join(project, "main.nc"), "w", encoding="utf-8") as f:
            f.write("fun main() {\n  bad()\n}\n")
        bad_path = os.path.join(project, "util.nc")
        with open(bad_path, "w", encoding="utf-8") as f:
            f.write("fun bad() {\n  let x: i32 = \"no\"\n}\n")

        result = run_nc("compile", project)

        assert result.returncode != 0
        assert bad_path in result.stderr
        assert ":2:3: let x: expected i32, got str" in result.stderr


def write_file(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_import_function_and_multifile_module_run():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        math = os.path.join(tmp, "math")
        os.mkdir(main)
        os.mkdir(math)
        write_file(os.path.join(main, "main.nc"), "import io\nimport math\nfun main() { io.println(math.add_twice(2, 3)) }\n")
        write_file(os.path.join(math, "a.nc"), "fun add_twice(a: i32, b: i32): i32 { return add(a, b) }\n")
        write_file(os.path.join(math, "b.nc"), "fun add(a: i32, b: i32): i32 { return a + b }\n")

        result = run_nc("run", main)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "5"


def test_import_struct_and_enum_run():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        model = os.path.join(tmp, "model")
        color = os.path.join(tmp, "color")
        os.mkdir(main)
        os.mkdir(model)
        os.mkdir(color)
        write_file(os.path.join(main, "main.nc"), """import model
import color
import io
fun main() {
  let u: model.User = model.User { age: 7 }
  let c: color.Color = color.pick()
  io.println(u.age)
}
""")
        write_file(os.path.join(model, "model.nc"), "struct User { age: i32 }\n")
        write_file(os.path.join(color, "color.nc"), "enum Color { Red, Blue }\nfun pick(): Color { return Color::Red }\n")

        result = run_nc("run", main)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "7"


def test_import_generic_function_and_struct_run():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        box = os.path.join(tmp, "box")
        os.mkdir(main)
        os.mkdir(box)
        write_file(os.path.join(main, "main.nc"), """import io
import box
fun main() {
  let a = box.id[i32](7)
  let b = box.Box[str] { value: "ok" }
  io.println(a)
  io.println(b.value)
}
""")
        write_file(os.path.join(box, "box.nc"), """fun id[T](x: T): T { x }
struct Box[T] { value: T }
""")

        result = run_nc("run", main)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "7\nok"


def test_import_iface_and_concrete_satisfaction_run():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        api = os.path.join(tmp, "api")
        impl = os.path.join(tmp, "impl")
        os.mkdir(main)
        os.mkdir(api)
        os.mkdir(impl)
        write_file(os.path.join(api, "api.nc"), "iface Writer { fun write(data: []u8): i32 }\n")
        write_file(os.path.join(impl, "impl.nc"), """struct File { value: i32 }
fun (f *File) write(data: []u8): i32 { f.value + i32(data[0]) }
fun make(): *File { new File { value: 40 } }
""")
        write_file(os.path.join(main, "main.nc"), """import io
import api
import impl
fun use(w: api.Writer): i32 { w.write([]u8 { 2u8 }) }
fun main() { io.println(use(impl.make())) }
""")

        result = run_nc("run", main)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "42"


def test_import_private_iface_error():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        api = os.path.join(tmp, "api")
        os.mkdir(main)
        os.mkdir(api)
        write_file(os.path.join(api, "api.nc"), "iface _Private { fun value(): i32 }\n")
        write_file(os.path.join(main, "main.nc"), "import api\nfun use(x: api._Private) {}\nfun main() {}\n")

        result = run_nc("compile", main)

        assert result.returncode != 0
        assert "symbol 'api._Private' is private" in result.stderr


def test_import_same_public_names_do_not_conflict():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        a = os.path.join(tmp, "a")
        b = os.path.join(tmp, "b")
        os.mkdir(main)
        os.mkdir(a)
        os.mkdir(b)
        write_file(os.path.join(main, "main.nc"), "import io\nimport a\nimport b\nfun value(): i32 { return 1 }\nfun main() { io.println(value() + a.value() + b.value()) }\n")
        write_file(os.path.join(a, "a.nc"), "fun value(): i32 { return 2 }\n")
        write_file(os.path.join(b, "b.nc"), "fun value(): i32 { return 3 }\n")

        result = run_nc("run", main)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "6"


def test_llvm_import_projects_run():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        math = os.path.join(tmp, "math")
        os.mkdir(main)
        os.mkdir(math)
        write_file(os.path.join(main, "main.nc"), "import io\nimport math\nfun main() { io.println(math.add_twice(2, 3)) }\n")
        write_file(os.path.join(math, "a.nc"), "fun add_twice(a: i32, b: i32): i32 { return add(a, b) }\n")
        write_file(os.path.join(math, "b.nc"), "fun add(a: i32, b: i32): i32 { return a + b }\n")
        result = run_nc("run", main)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "5"

    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        model = os.path.join(tmp, "model")
        color = os.path.join(tmp, "color")
        os.mkdir(main)
        os.mkdir(model)
        os.mkdir(color)
        write_file(os.path.join(main, "main.nc"), """import model
import color
import io
fun main() {
  let u: model.User = model.User { age: 7 }
  let c: color.Color = color.pick()
  io.println(u.age)
}
""")
        write_file(os.path.join(model, "model.nc"), "struct User { age: i32 }\n")
        write_file(os.path.join(color, "color.nc"), "enum Color { Red, Blue }\nfun pick(): Color { return Color::Red }\n")
        result = run_nc("run", main)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "7"

    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        a = os.path.join(tmp, "a")
        b = os.path.join(tmp, "b")
        os.mkdir(main)
        os.mkdir(a)
        os.mkdir(b)
        write_file(os.path.join(main, "main.nc"), "import io\nimport a\nimport b\nfun value(): i32 { return 1 }\nfun main() { io.println(value() + a.value() + b.value()) }\n")
        write_file(os.path.join(a, "a.nc"), "fun value(): i32 { return 2 }\n")
        write_file(os.path.join(b, "b.nc"), "fun value(): i32 { return 3 }\n")
        result = run_nc("run", main)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "6"

    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        box = os.path.join(tmp, "box")
        os.mkdir(main)
        os.mkdir(box)
        write_file(os.path.join(main, "main.nc"), """import io
import box
fun main() {
  let a = box.id[i32](7)
  let b = box.Box[str] { value: "ok" }
  io.println(a)
  io.println(b.value)
}
""")
        write_file(os.path.join(box, "box.nc"), """fun id[T](x: T): T { x }
struct Box[T] { value: T }
""")
        result = run_nc("run", main)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "7\nok"


def test_backend_option_is_removed():
    result = run_nc("build", "--backend", "c", os.path.join("test_cases", "case_170_generics_identity.nc"))
    assert result.returncode != 0
    assert "C backend 已删除" in result.stderr
    assert "LLVM 是唯一后端" in result.stderr


def test_import_private_symbol_error():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        foo = os.path.join(tmp, "foo")
        os.mkdir(main)
        os.mkdir(foo)
        write_file(os.path.join(main, "main.nc"), "import io\nimport foo\nfun main() { io.println(foo._helper()) }\n")
        write_file(os.path.join(foo, "foo.nc"), "fun _helper(): i32 { return 1 }\n")

        result = run_nc("compile", main)

        assert result.returncode != 0
        assert "symbol 'foo._helper' is private" in result.stderr


def test_import_missing_empty_cycle_and_nested_import_errors():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        os.mkdir(main)
        write_file(os.path.join(main, "main.nc"), "import missing\nfun main() {}\n")
        result = run_nc("compile", main)
        assert result.returncode != 0
        assert "module 'missing' not found" in result.stderr

        empty = os.path.join(tmp, "empty")
        os.mkdir(empty)
        write_file(os.path.join(main, "main.nc"), "import empty\nfun main() {}\n")
        result = run_nc("compile", main)
        assert result.returncode != 0
        assert "module 'empty' has no .nc files" in result.stderr

        a = os.path.join(tmp, "a")
        os.mkdir(a)
        write_file(os.path.join(main, "main.nc"), "import a\nfun main() {}\n")
        write_file(os.path.join(a, "a.nc"), "import main\n")
        result = run_nc("compile", main)
        assert result.returncode != 0
        assert "import cycle: main -> a -> main" in result.stderr

        write_file(os.path.join(main, "main.nc"), "import foo.bar\nfun main() {}\n")
        result = run_nc("compile", main)
        assert result.returncode != 0
        assert "import v1 only supports one-level module names" in result.stderr


def test_import_not_visible_without_namespace_and_not_allowed_in_block():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        foo = os.path.join(tmp, "foo")
        os.mkdir(main)
        os.mkdir(foo)
        write_file(os.path.join(foo, "foo.nc"), "fun add(): i32 { return 1 }\n")
        write_file(os.path.join(main, "main.nc"), "import io\nimport foo\nfun main() { io.println(add()) }\n")
        result = run_nc("compile", main)
        assert result.returncode != 0
        assert "Function 'add' not found" in result.stderr

        write_file(os.path.join(main, "main.nc"), "fun main() { import foo }\n")
        result = run_nc("compile", main)
        assert result.returncode != 0
        assert "import is only allowed at top level" in result.stderr


def test_builtin_io_module_println_run_without_directory():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        os.mkdir(main)
        write_file(os.path.join(main, "main.nc"), "import io\nfun main() { io.println(1) }\n")

        result = run_nc("run", main)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "1"


def test_builtin_io_module_preempts_sibling_directory():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        io_dir = os.path.join(tmp, "io")
        os.mkdir(main)
        os.mkdir(io_dir)
        write_file(os.path.join(main, "main.nc"), "import io\nfun main() { io.println(1) }\n")
        write_file(os.path.join(io_dir, "io.nc"), "fun println(x: i32) { bad() }\n")

        result = run_nc("run", main)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "1"


def test_builtin_runtime_module_preempts_sibling_directory():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        runtime_dir = os.path.join(tmp, "runtime")
        os.mkdir(main)
        os.mkdir(runtime_dir)
        write_file(os.path.join(main, "main.nc"), "import runtime\nfun main() { runtime.gc_collect() }\n")
        write_file(os.path.join(runtime_dir, "runtime.nc"), "fun gc_collect() { bad() }\n")

        result = run_nc("run", main)

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == ""


def test_bare_print_and_unimported_io_println_errors():
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main")
        os.mkdir(main)

        write_file(os.path.join(main, "main.nc"), "fun main() { print(1) }\n")
        result = run_nc("compile", main)
        assert result.returncode != 0
        assert "Function 'print' not found" in result.stderr

        write_file(os.path.join(main, "main.nc"), "fun main() { io.println(1) }\n")
        result = run_nc("compile", main)
        assert result.returncode != 0
        assert "Variable 'io' not found" in result.stderr
