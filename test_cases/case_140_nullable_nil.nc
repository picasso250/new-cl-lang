import io
# STDOUT: 3
struct Point { x: i32 }

fun main() {
    let p: ?*Point = nil
    let q: ?*Point = new Point { x: 3 }
    if p != nil {
        io.println(p.x)
    }
    if q != nil {
        io.println(q.x)
    }
}
