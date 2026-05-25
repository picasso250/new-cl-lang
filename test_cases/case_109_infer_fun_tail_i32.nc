import io
# STDOUT: 7

fun add(x: i32, y: i32) {
    x + y
}

fun main() {
    io.println(add(3, 4))
}
