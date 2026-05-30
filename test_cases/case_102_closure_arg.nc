import io
# STDOUT: 8
fun apply(f: fun(i32) i32, x: i32): i32 {
    f(x)
}

fun main() {
    let base = 3
    let add = fun(x: i32): i32 { x + base }
    io.println(apply(add, 5))
}
