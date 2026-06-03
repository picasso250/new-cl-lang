import io
# STDOUT: 16
# STDOUT: 26
# STDOUT: 36

fun sum(a: i32, b: i32 = 10, c: i32 = 5): i32 {
    a + b + c
}

fun main() {
    io.println(sum(1))
    io.println(sum(1, 20))
    io.println(sum(1, 20, 15))
}
