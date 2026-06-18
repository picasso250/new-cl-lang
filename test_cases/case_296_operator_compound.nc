import io
# STDOUT: 6

struct Vec { x: i32 }

fun (v *Vec) __add__(other: Vec): Vec {
    Vec { x: v.x + other.x }
}

fun main() {
    let a = Vec { x: 2 }
    a += Vec { x: 4 }
    io.println(a.x)
}
