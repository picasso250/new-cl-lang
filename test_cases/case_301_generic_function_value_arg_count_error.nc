# ERROR: generic function less: expected 1 type args, got 2
import types

fun less[T types.Ord](a: T, b: T): bool { a < b }

fun main() {
    let f = less[i32, i64]
}
