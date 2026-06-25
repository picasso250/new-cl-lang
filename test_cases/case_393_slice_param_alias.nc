import io
# STDOUT: 2

fun f(a: []i32, b: []i32): i32 {
    a[0] = 1
    b[0] = 2
    ret a[0]
}

fun main() {
    let xs = []i32 { 0 }
    io.println(f(xs, xs))
}
