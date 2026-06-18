import io
# STDOUT: 10

fun apply(x: i32, f: fun(i32) i32): i32 {
    ret f(x)
}

fun main() {
    let f = fun(x: i32) { x + 3 }
    io.println(apply(7, f))
}
