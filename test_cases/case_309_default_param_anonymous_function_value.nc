import io

# STDOUT: 1

fun apply(cmp: fun(i32, i32) bool = fun(a: i32, b: i32): bool { a < b }): bool {
    cmp(1, 2)
}

fun main() {
    io.println(apply())
}
