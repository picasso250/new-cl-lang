# ERROR: operator method Vec.__neg__: expected no parameters
struct Vec { x: i32 }

fun (v *Vec) __neg__(other: Vec): Vec {
    Vec { x: 0 }
}

fun main() {
    -(Vec { x: 1 })
}
