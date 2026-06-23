import io
import types
# STDOUT: 1

struct Box { x: i32 }

fun (b *Box) __lt__(other: Box): bool {
    b.x < other.x
}

fun less[T types.Ord](a: T, b: T): bool {
    a < b
}

fun main() {
    io.println(less[Box](Box { x: 1 }, Box { x: 2 }))
}
