# ERROR: comparison: expected numeric operands, got Box and Box
struct Box { x: i32 }

fun (b *Box) __le__(other: Box): bool {
    b.x <= other.x
}

fun main() {
    let a = Box { x: 1 }
    let b = Box { x: 2 }
    b > a
}
