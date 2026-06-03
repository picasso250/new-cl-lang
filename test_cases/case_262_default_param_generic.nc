import io
# STDOUT: 7
# STDOUT: 9

fun choose[T any](a: T, b: T = a): T {
    b
}

fun main() {
    io.println(choose[i32](7))
    io.println(choose[i32](7, 9))
}
