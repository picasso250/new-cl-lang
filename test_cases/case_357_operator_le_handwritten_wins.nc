import io
# STDOUT: 0
# STDOUT: 1

struct Box { x: i32 }

fun (b *Box) __lt__(other: Box): bool {
    b.x < other.x
}

fun (b *Box) __le__(other: Box): bool {
    false
}

fun main() {
    let a = Box { x: 1 }
    let b = Box { x: 2 }
    io.println(a <= b)
    io.println(b >= a)
}
