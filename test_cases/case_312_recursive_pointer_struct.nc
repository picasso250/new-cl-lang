import io
# STDOUT: 2
# STDOUT: 16
struct A { b: ?*B, value: i32 }
struct B { a: ?*A, value: i32 }

fun main() {
    let a = new A { b: nil, value: 1 }
    let b = new B { a: a, value: 2 }
    a.b = b
    let bb = a.b
    if bb != nil {
        io.println(bb.value)
    }
    io.println(size_of(A))
}
