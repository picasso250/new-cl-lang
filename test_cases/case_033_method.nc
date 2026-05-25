import io
# STDOUT: 42

struct Point { x: i32, y: i32 }

fun (p *Point) get_x(): i32 {
    return p.x
}

fun main() {
    let p = new Point { x: 42, y: 0 }
    io.println(p.get_x())
}
