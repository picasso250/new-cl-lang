import io
# ERROR: struct Point: missing field y
struct Point { x: i32, y: i32 }

fun main() {
    let p = Point { x: 3 }
    io.println(p.x)
}
