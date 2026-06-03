# ERROR: unknown generic constraint types.Cmp

import types

fun old[T types.Cmp](x: T): T { x }

fun main() {
    old[i32](1)
}
