import io
# STDOUT: 7
# STDOUT: 7

struct A { x: i32 }
struct B { A, y: i32 }

fun main() {
    let b = B { A: A { x: 7 }, y: 2 }
    io.println(b.A.x)
    io.println(b.x)
}
