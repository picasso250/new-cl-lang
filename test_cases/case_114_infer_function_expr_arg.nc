import io
# STDOUT: 10

fun apply(x: i32, f: (i32) -> i32): i32 {
    return f(x)
}

fun main() {
    let f = fun(x: i32) { x + 3 }
    io.println(apply(7, f))
}
