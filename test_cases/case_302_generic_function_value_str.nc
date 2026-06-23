import io
import types

fun less[T types.Ord](a: T, b: T): bool { a < b }

fun main() {
    let f = less[str]
    io.println(f("a", "b"))
}

# STDOUT: 1
