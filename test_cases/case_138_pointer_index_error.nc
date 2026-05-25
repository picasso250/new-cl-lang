import io
# ERROR: pointer type *Point: indexing is not allowed
struct Point { x: i32 }

fun main() {
    let p = new Point { x: 1 }
    io.println(p[0].x)
}
