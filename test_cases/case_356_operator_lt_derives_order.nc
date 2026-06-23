import io
# STDOUT: 1
# STDOUT: 1
# STDOUT: 1
# STDOUT: 1

struct Box { x: i32 }

fun (b *Box) __lt__(other: Box): bool {
    b.x < other.x
}

fun main() {
    let a = Box { x: 1 }
    let b = Box { x: 2 }
    io.println(a < b)
    io.println(a <= b)
    io.println(b > a)
    io.println(b >= a)
}
