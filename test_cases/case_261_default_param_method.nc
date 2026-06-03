import io
# STDOUT: 3
# STDOUT: 5

struct Point { x: i32 }

fun (p *Point) move(dx: i32 = 0): i32 {
    p.x + dx
}

fun main() {
    let p = new Point { x: 3 }
    io.println(p.move())
    io.println(p.move(2))
}
