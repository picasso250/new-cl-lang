import io
# STDOUT: 9
# STDOUT: 9

iface Getter { fun get(): i32 }

struct A { x: i32 }
struct B { A, y: i32 }

fun (a *A) get(): i32 { a.x }

fun use(g: Getter): i32 { g.get() }

fun main() {
    let b = B { A: A { x: 9 }, y: 1 }
    io.println(b.get())
    io.println(use(new B { A: A { x: 9 }, y: 1 }))
}
