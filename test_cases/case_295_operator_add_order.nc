import io
# STDOUT: 7
# STDOUT: 1

struct Vec { x: i32 }

fun (v *Vec) __add__(other: Vec): Vec {
    Vec { x: v.x + other.x }
}

fun (v *Vec) __lt__(other: Vec): bool {
    v.x < other.x
}

fun main() {
    let a = Vec { x: 3 }
    let b = Vec { x: 4 }
    let c = a + b
    io.println(c.x)
    io.println(a < b)
}
