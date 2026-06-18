import io
# STDOUT: 7
fun add(x: i32, y: i32): i32 {
    ret x + y
}

fun main() {
    let x: i32 = 3
    let y: i32 = 4
    io.println(add(x, y))
}
