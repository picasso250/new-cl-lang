import io
# STDOUT: 9
struct Point { x: i32, y: i32 }

fun main() {
    let p = new Point { x: 1, y: 2 }
    p.x = 7
    io.println(p.x + p.y)
}
