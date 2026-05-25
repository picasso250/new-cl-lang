# STDOUT: 1
struct Point { x: i32 }

fun same(a: *Point, b: *Point): bool {
    a == b
}

fun main() {
    let p = new Point { x: 1 }
    if same(p, p) {
        print(1)
    } else {
        print(0)
    }
}
