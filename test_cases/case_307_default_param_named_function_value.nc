import io

# STDOUT: 1
# STDOUT: 0

fun less(a: i32, b: i32): bool {
    a < b
}

fun apply(cmp: fun(i32, i32) bool = less): bool {
    cmp(1, 2)
}

fun main() {
    io.println(apply())
    io.println(apply(fun(a: i32, b: i32): bool { a > b }))
}
