import io
# STDOUT: 1

struct Vec { x: i32 }

fun (v *Vec) __eq__(other: Vec): bool {
    false
}

fun main() {
    let a = Vec { x: 1 }
    let b = Vec { x: 1 }
    io.println(a == b)
}
