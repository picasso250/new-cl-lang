# ERROR: generic function less: type arg Box does not satisfy types.Ord
import types

struct Box { x: i32 }

fun (b *Box) __le__(other: Box): bool {
    b.x <= other.x
}

fun less[T types.Ord](a: T, b: T): bool {
    a < b
}

fun main() {
    less[Box](Box { x: 1 }, Box { x: 2 })
}
