import io
# STDOUT: 24

struct S { a: u8, b: [3]i32, c: u8 }

fun main() {
    io.println(size_of(S))
}
