import io
import types

fun min_ord[T types.Ord](a: T, b: T): T { if a < b { a } else { b } }

fun main() {
    io.println(min_ord[str]("b", "a"))
}

# STDOUT: a
