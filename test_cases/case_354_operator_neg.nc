import io
# STDOUT: -7

struct Vec { x: i32 }

fun (v *Vec) __neg__(): Vec {
    Vec { x: -v.x }
}

fun main() {
    let v = Vec { x: 7 }
    let n = -v
    io.println(n.x)
}
