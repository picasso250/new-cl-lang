import io
import types

fun less[T types.Ord](a: T, b: T): bool { a < b }

fun apply(f: fun(i32, i32) bool, a: i32, b: i32): bool {
    f(a, b)
}

fun main() {
    let f: fun(i32, i32) bool = less[i32]
    io.println(f(1, 2))
    io.println(apply(less[i32], 3, 2))
}

# STDOUT: 1
# STDOUT: 0
