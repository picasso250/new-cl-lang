import io
# STDOUT: 12

fun grow(a: i32, b: i32 = a + 1, c: i32 = b + 1): i32 {
    a + b + c
}

fun main() {
    io.println(grow(3))
}
