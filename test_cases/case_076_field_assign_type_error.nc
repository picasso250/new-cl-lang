# ERROR: assignment: expected i32, got str
struct Point { x: i32, y: i32 }

fun main() {
    let p = Point { x: 1, y: 2 }
    p.x = "bad"
    print(p.x)
}
