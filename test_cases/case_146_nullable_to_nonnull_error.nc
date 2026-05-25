import io
# ERROR: let q: expected *Point, got ?*Point
struct Point { x: i32 }

fun main() {
    let p: ?*Point = new Point { x: 1 }
    let q: *Point = p
    io.println(q.x)
}
