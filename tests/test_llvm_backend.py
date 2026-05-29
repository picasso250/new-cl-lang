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


def test_llvm_println_string_literal_and_variable():
    source = """import io
fun main() {
    io.println("hello")
    let name: str = "nc"
    io.println(name)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("hello\nnc", "", 0)


def test_llvm_string_len_and_equality():
    source = """import io
fun main() {
    let a: str = "same"
    let b: str = "same"
    let c: str = "diff"
    io.println(len(a))
    io.println(a == b)
    io.println(a != c)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("4\n1\n1", "", 0)


def test_llvm_numeric_casts():
    source = """import io
fun main() {
    let a: i32 = 42
    let b: i64 = i64(a)
    let c: f64 = f64(b)
    let d: u8 = u8(a)
    io.println(b)
    io.println(c)
    io.println(d)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("42\n42\n42", "", 0)


def test_llvm_string_numeric_casts():
    source = """import io
fun main() {
    let s = str(42)
    io.println(s)
    io.println("hello" + str(99))
    io.println(i32("123") + 1)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("42\nhello99\n124", "", 0)


def test_llvm_array_literal_and_index():
    source = """import io
fun main() {
    let x: i32 = 2
    let arr = [3]i32 { 1, x, 3 }
    io.println(arr[0] + arr[1] + arr[2])
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("6", "", 0)


def test_llvm_array_index_assignment():
    source = """import io
fun main() {
    let arr = [3]i32 { 1, 2, 3 }
    arr[1] = 7
    io.println(arr[0] + arr[1] + arr[2])
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("11", "", 0)


def test_llvm_struct_literal_field_access_and_assign():
    source = """import io
fun main() {
    struct Point { x: i32, y: i32 }
    let p = Point { y: 4, x: 3 }
    io.println(p.x)
    p.y = 9
    io.println(p.y)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("3\n9", "", 0)


def test_llvm_struct_param_and_return():
    source = """import io
struct Pair { a: i32, b: i32 }
fun make_pair(): Pair { return Pair { a: 2, b: 5 } }
fun move(p: Pair, delta: i32): Pair { Pair { a: p.a + delta, b: p.b } }
fun sum(p: Pair): i32 { p.a + p.b }
fun main() {
    let p = move(make_pair(), 1)
    io.println(sum(p))
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("8", "", 0)


def test_llvm_heap_struct_method_call():
    source = """import io
struct Point { x: i32, y: i32 }
fun (p *Point) sum(delta: i32): i32 {
    return p.x + p.y + delta
}
fun main() {
    let p = new Point { x: 20, y: 21 }
    io.println(p.sum(1))
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("42", "", 0)


def test_llvm_enum_and_match():
    source = """import io
fun main() {
    enum Color { Red, Green, Blue }
    let c = Color::Green
    if c == Color::Green { io.println(1) }
    let result = match c {
        Color::Red -> 10
        Color::Green -> 20
        Color::Blue -> 30
    }
    io.println(result)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("1\n20", "", 0)


def test_llvm_match_else_string_result():
    source = """import io
fun main() {
    let n = 3
    let label = match n {
        0 -> "zero"
        1 -> "one"
        else -> "many"
    }
    io.println(label)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("many", "", 0)


def test_llvm_block_expr_call_arg_and_match_arm():
    source = """import io
fun add1(x: i32): i32 { x + 1 }
fun main() {
    let x = {
        let a = 2
        a + 3
    }
    io.println(add1({
        let a = 7
        a
    }))
    let n = 1
    let result = match n {
        0 -> 0
        else -> {
            let base = x
            base + 2
        }
    }
    io.println(result)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("8\n7", "", 0)


def test_llvm_tail_match_return():
    source = """import io
fun describe(n: i32): str {
    match n {
        0 -> "zero"
        1 -> "one"
        else -> "many"
    }
}
fun main() { io.println(describe(1)) }
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("one", "", 0)


def test_llvm_range_for():
    source = """import io
fun main() {
    let sum = 0
    for i in 0..4 {
        sum = sum + i
    }
    io.println(sum)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("6", "", 0)


def test_llvm_slice_literal_len_index_and_param_return():
    source = """import io
fun second(xs: []i32): i32 { xs[1] }
fun same(xs: []i32): []i32 { xs }
fun main() {
    let s = []i32 { 10, 20, 30 }
    let t = same(s)
    io.println(len(t))
    io.println(second(t) + t[2])
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("3\n50", "", 0)


def test_llvm_array_slice_copy():
    source = """import io
fun main() {
    let arr = [3]i32 { 10, 20, 30 }
    let s = arr[0:3]
    io.println(len(s))
    io.println(s[0] + s[1] + s[2])
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("3\n60", "", 0)


def test_llvm_slice_for_in():
    source = """import io
fun main() {
    let s = []i32 { 10, 20, 30 }
    for i, item in s {
        io.println(i + item)
    }
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("10\n21\n32", "", 0)


def test_llvm_slice_append_and_reslice_copy():
    source = """import io
fun grow(xs: []i32): []i32 {
    append(xs, 4)
}
fun main() {
    let base = []i32 { 10, 20, 30, 40 }
    let s1 = base[1:3]
    s1[1] = 99
    let s2 = append(s1, 77)
    io.println(base[2])
    io.println(s2[0] + s2[1] + s2[2] + len(s2))
    let xs = []i32 { 1, 2, 3 }
    let ys = grow(xs)
    io.println(ys[1] + ys[3] + len(ys))
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("30\n199\n10", "", 0)


def test_llvm_slice_append_str():
    source = """import io
fun main() {
    let s = []str { "a", "b" }
    s = append(s, "c")
    for i, item in s {
        io.println(item)
    }
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("a\nb\nc", "", 0)


def test_llvm_string_index_slice_and_concat():
    source = """import io
fun main() {
    let s = "hello"
    io.println(s[1])
    let sub = s[1:5]
    io.println(sub)
    let c = "hello" + "world"
    io.println(c)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("101\nello\nhelloworld", "", 0)


def test_llvm_break_in_loops():
    source = """import io
fun main() {
    let s = "hello"
    io.println(len(s))
    for i in 0..10 {
        if i == 3 { break }
        io.println(i)
    }
    let xs = []i32 { 10, 20, 30 }
    for i, item in xs {
        if i == 1 { break }
        io.println(item)
    }
    let x = 0
    for x < 3 {
        break
        io.println(99)
    }
    io.println(7)
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("5\n0\n1\n2\n10\n7", "", 0)


def test_llvm_file_io(tmp_path):
    path = str(tmp_path / "llvm_file_io.txt").replace("\\", "/")
    source = f"""import io
fun main() {{
    write_file("{path}", "hello")
    let content = read_file("{path}")
    io.println(content)
}}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("hello", "", 0)


def test_llvm_map_basic_and_growth():
    assignments = "\n".join([f'    m["k{i}"] = "v{i}"' for i in range(20)])
    source = f"""import io
fun main() {{
    let m = map_new()
{assignments}
    m["k1"] = "updated"
    io.println(len(m))
    io.println(map_has(m, "k19"))
    io.println(m["k19"])
    io.println(m["k1"])
    io.println(map_has(m, "missing"))
}}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("20\n1\nv19\nupdated\n0", "", 0)


def test_llvm_temporary_gc_hooks():
    source = """import io
import runtime
fun main() {
    let s = str(42)
    runtime.gc_collect()
    io.println(s)
    runtime.gc_live()
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("42\n1", "", 0)


def test_llvm_gc_live_tracks_allocator_hook():
    source = """import runtime
fun main() {
    let a = str(1)
    let b = "x" + "y"
    runtime.gc_live()
    runtime.gc_collect()
    runtime.gc_live()
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("2\n2", "", 0)


def test_llvm_gc_collect_releases_dead_helper_locals():
    source = """import runtime
fun helper() {
    let a = str(1)
    let b = "x" + "y"
    runtime.gc_live()
}
fun main() {
    helper()
    runtime.gc_collect()
    runtime.gc_live()
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("2\n0", "", 0)


def test_llvm_uses_external_ncrt_runtime():
    llvm_ir = compile_nc_to_llvm_ir("""import io
import runtime
fun main() {
    let m = map_new()
    m["a"] = "b"
    io.println(m["a"])
    runtime.gc_live()
}
""")

    assert 'define i8* @"__nc_gc_alloc"' not in llvm_ir
    assert 'declare i8* @"__nc_gc_alloc"' in llvm_ir
    assert "__nc_map_get_str_out" in llvm_ir


def test_llvm_throw_try_catch_and_uncaught():
    source = """import io
fun risky(path: str): str {
    if path == "" {
        throw "bad path"
    }
    return "ok"
}
fun main() {
    try {
        let s = risky("")
        io.println(s)
    } catch e {
        io.println("error: " + e)
    }
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("error: bad path", "", 0)

    llvm_ir = compile_nc_to_llvm_ir('fun main() { throw "boom" }')
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("", "uncaught: boom", 1)


def test_llvm_defer_lifo_return_and_throw():
    source = """import io
fun main(): i32 {
    defer { io.println(1) }
    defer { io.println(2) }
    io.println(3)
    return 7
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("3\n2\n1", "", 7)

    source = """import io
import runtime
fun fail() {
    defer { runtime.gc_collect() }
    throw str(1)
}
fun main() {
    try {
        fail()
    } catch e {
        runtime.gc_collect()
        io.println(e)
    }
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("1", "", 0)


def test_llvm_no_capture_closure_call():
    source = """import io
fun main() {
    let inc = fun(x: i32): i32 { x + 1 }
    io.println(inc(5))
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("6", "", 0)


def test_llvm_capturing_closure_values_args_and_return():
    source = """import io
fun apply(f: (i32) -> i32, x: i32): i32 { f(x) }
fun make(base: i32): (i32) -> i32 {
    let xs = []i32 { 10, 20, 30 }
    fun(x: i32): i32 { x + base + xs[1] }
}
fun main() {
    let base = 10
    let add = fun(x: i32): i32 { x + base }
    base = 99
    io.println(add(5))
    io.println(apply(add, 7))
    let f = make(2)
    io.println(f(3))
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("15\n17\n25", "", 0)


def test_llvm_nullable_pointer_nil_and_method():
    source = """import io
struct Point { x: i32 }
fun (p *Point) value(): i32 { p.x }
fun pick(p: ?*Point): i32 {
    if nil != p {
        p.value()
    } else {
        0
    }
}
fun main() {
    let p: ?*Point = nil
    let q: ?*Point = new Point { x: 7 }
    if p != nil { io.println(p.x) }
    io.println(pick(q))
}
"""
    llvm_ir = compile_nc_to_llvm_ir(source)
    stdout, stderr, rc = run_llvm_ir(llvm_ir)
    assert (stdout.strip(), stderr.strip(), rc) == ("7", "", 0)


def test_llvm_build_writes_ir_obj_and_exe(tmp_path):
    llvm_ir = compile_nc_to_llvm_ir("import io\nfun main() { io.println(42) }")
    ll_path, obj_path, exe_path = build_llvm_ir(llvm_ir, str(tmp_path), "main")
    assert os.path.exists(ll_path)
    assert os.path.exists(obj_path)
    assert os.path.exists(tmp_path / "ncrt.obj")
    assert os.path.exists(exe_path)
    result = subprocess.run([exe_path], capture_output=True, text=True)
    assert result.stdout.strip() == "42"
    assert result.returncode == 0
