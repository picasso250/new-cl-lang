import io
# STDOUT: 3
# STDOUT: 7

fun add(a: i32, b: i32 = 0): i32 {
    a + b
}

fun main() {
    io.println(add(3))
    io.println(add(3, 4))
}
