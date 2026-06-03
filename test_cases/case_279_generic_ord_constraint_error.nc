# ERROR: generic function min_ord: type arg str does not satisfy types.Ord

import types

fun min_ord[T types.Ord](a: T, b: T): T { if a < b { a } else { b } }

fun main() {
    min_ord[str]("a", "b")
}
