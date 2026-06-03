import io
# STDOUT: 1
# STDOUT: 1
struct Point { x: i32, y: i32 }

fun main() {
    let a = Point { x: 1, y: 2 }
    let b = Point { x: 1, y: 2 }
    let c = Point { x: 1, y: 3 }
    io.println(a == b)
    io.println(a != c)
}
