import io
# STDOUT: 2
# STDOUT: 30

struct S { a: u8, b: [3]i32, c: u8 }

fun main() {
    let p = new S { a: 1u8, b: [3]i32 { 10, 20, 30 }, c: 2u8 }
    io.println(p.c)
    io.println(p.b[2])
}
