# ERROR: struct Point: duplicate field x
struct Point { x: i32, y: i32 }

fun main() {
    let p = Point { x: 3, x: 4, y: 5 }
    print(p.x)
}
