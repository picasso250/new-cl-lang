# ERROR: pointer type *Point: operator < is not allowed
struct Point { x: i32 }

fun main() {
    let a = new Point { x: 1 }
    let b = new Point { x: 2 }
    if a < b {
        print(1)
    }
}
