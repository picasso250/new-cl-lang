# ERROR: pointer type *Point: indexing is not allowed
struct Point { x: i32 }

fun main() {
    let p = new Point { x: 1 }
    print(p[0].x)
}
