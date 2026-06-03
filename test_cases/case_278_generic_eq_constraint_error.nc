# ERROR: generic function same: type arg Bad does not satisfy types.Eq

import types

struct Bad {
    xs: []i32
}

fun same[T types.Eq](a: T, b: T): bool { a == b }

fun main() {
    same[Bad](Bad { xs: []i32 { 1 } }, Bad { xs: []i32 { 1 } })
}
