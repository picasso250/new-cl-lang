import io
# STDOUT: 7
struct Point { x: i32, y: i32 }

fun main() {
    let p = Point { y: 4, x: 3 }
    io.println(p.x + p.y)
}
