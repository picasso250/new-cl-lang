# STDOUT: 7
struct Point { x: i32, y: i32 }

fun main() {
    let p = Point { y: 4, x: 3 }
    print(p.x + p.y)
}
