import io
# STDOUT: 10
fun grow(xs: []i32): []i32 {
    append(xs, 4)
}

fun main() {
    let xs = []i32 { 1, 2, 3 }
    let ys = grow(xs)
    io.println(ys[1] + ys[3] + len(ys))
}
