# ERROR: generic function less: type arg str does not satisfy types.Ord
import types

fun less[T types.Ord](a: T, b: T): bool { a < b }

fun main() {
    let f = less[str]
}
