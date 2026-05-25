import io
# ERROR: cannot assign to narrowed nullable pointer 'p' inside non-nil block
struct Point { x: i32 }

fun main() {
    let p: ?*Point = new Point { x: 1 }
    if p != nil {
        p = nil
        io.println(p.x)
    }
}
