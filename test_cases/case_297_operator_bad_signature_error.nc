# ERROR: operator method Vec.__add__: expected one parameter
struct Vec { x: i32 }

fun (v *Vec) __add__(): Vec {
    v
}

fun main() {
    let a = Vec { x: 1 }
    let b = Vec { x: 2 }
    a + b
}
