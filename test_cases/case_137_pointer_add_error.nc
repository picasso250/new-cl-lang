# ERROR: pointer type *Point: operator + is not allowed
struct Point { x: i32 }

fun main() {
    let p = new Point { x: 1 }
    let q = p + 1
    print(q.x)
}
