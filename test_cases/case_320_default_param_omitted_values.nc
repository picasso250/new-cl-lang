import io

# STDOUT: x
# STDOUT: 7
# STDOUT: 3
# STDOUT: 7
# STDOUT: 1
# STDOUT: 42
# STDOUT: 42

struct Box { value: i32 }

fun take_scalar(x = 7): i32 {
    x
}

fun take_str(s = "x"): str {
    s
}

fun take_slice(xs = []i32 { 1, 2, 3 }): i32 {
    len(xs)
}

fun take_struct(b = Box { value: 7 }): i32 {
    b.value
}

fun take_map(m = map[str,i32]{}): i32 {
    m["a"] = 1
    m["a"]
}

fun take_i64(x = i64(42)): i64 {
    x
}

fun take_string(s = str(42)): str {
    s
}

fun main() {
    io.println(take_str())
    io.println(take_scalar())
    io.println(take_slice())
    io.println(take_struct())
    io.println(take_map())
    io.println(take_i64())
    io.println(take_string())
}
