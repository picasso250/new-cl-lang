import io

# STDOUT: 1
# STDOUT: 1

fun less(a: i32, b: i32): bool {
    a < b
}

fun apply_named(cmp = less): bool {
    cmp(1, 2)
}

fun apply_anon(cmp = fun(a: i32, b: i32): bool { a < b }): bool {
    cmp(1, 2)
}

fun main() {
    io.println(apply_named())
    io.println(apply_anon())
}
