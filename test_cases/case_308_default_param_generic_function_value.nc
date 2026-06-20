import io
import types

# STDOUT: 1

fun less[T types.Ord](a: T, b: T): bool {
    a < b
}

fun apply(cmp: fun(i32, i32) bool = less[i32]): bool {
    cmp(1, 2)
}

fun main() {
    io.println(apply())
}
