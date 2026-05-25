import io
# STDOUT: 7
struct Point { x: i32, y: i32 }

fun move(p: Point, dx: i32): Point {
    Point { x: p.x + dx, y: p.y }
}

fun main() {
    let p = Point { x: 2, y: 3 }
    let q = move(p, 2)
    io.println(q.x + q.y)
}
