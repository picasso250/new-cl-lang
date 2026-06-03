import io
import types

fun min2[T types.Cmp](a: T, b: T): T {
    if a < b { a } else { b }
}

fun main() {
    io.println(min2[i32](7, 3))
    io.println(min2[f64](2.5, 4.0))
}

# STDOUT: 3
# STDOUT: 2.5
