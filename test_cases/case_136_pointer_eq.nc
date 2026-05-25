import io
# STDOUT: 1
struct Point { x: i32 }

fun same(a: *Point, b: *Point): bool {
    a == b
}

fun main() {
    let p = new Point { x: 1 }
    if same(p, p) {
        io.println(1)
    } else {
        io.println(0)
    }
}
