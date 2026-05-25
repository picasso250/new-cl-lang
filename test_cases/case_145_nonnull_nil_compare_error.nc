# ERROR: nil comparison requires nullable pointer, got *Point
struct Point { x: i32 }

fun main() {
    let p = new Point { x: 1 }
    if p == nil {
        print(0)
    }
}
