# ERROR: let p: expected *Point, got __nil
struct Point { x: i32 }

fun main() {
    let p: *Point = nil
}
