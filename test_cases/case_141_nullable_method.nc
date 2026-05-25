import io
# STDOUT: 7
struct Point { x: i32 }

fun (p *Point) value(): i32 {
    p.x
}

fun f(p: ?*Point): i32 {
    if nil != p {
        p.value()
    } else {
        0
    }
}

fun main() {
    let p = new Point { x: 7 }
    let q: ?*Point = p
    io.println(f(q))
}
