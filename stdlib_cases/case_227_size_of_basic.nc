# STDOUT: 1
# STDOUT: 4
# STDOUT: 8
# STDOUT: 8
# STDOUT: 1
# STDOUT: 4
# STDOUT: 16
# STDOUT: 8
# STDOUT: 8
# STDOUT: 24
# STDOUT: 40
# STDOUT: 12
# STDOUT: 16
# STDOUT: 32
# STDOUT: 16
import io

struct P { a: u8, b: u64 }

fun inc(x: i32): i32 { x + 1 }

fun main() {
    io.println(size_of(i8))
    io.println(size_of(i32))
    io.println(size_of(i64))
    io.println(size_of(f64))
    io.println(size_of(bool))
    io.println(size_of(rune))
    io.println(size_of(str))
    io.println(size_of(*P))
    io.println(size_of(?*P))
    io.println(size_of([]i32))
    io.println(size_of(map[str,i32]))
    io.println(size_of([3]i32))
    io.println(size_of(P))
    io.println(size_of([2]P))
    io.println(size_of(fun(i32) i32))
}
