import io
# STDOUT: 7
struct Point { x: i32, y: i32 }

fun main() {
    let p = Point { x: 1, y: 2 }
    p.x = 5
    io.println(p.x + p.y)
}
