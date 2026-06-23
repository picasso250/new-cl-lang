import io
# STDOUT: 1
# STDOUT: 1

struct Node { value: i32 }

fun main() {
    let n = new Node { value: 11 }
    let p: ?*Node = n
    let m = map[?*Node,?*Node]{}
    m[p] = p
    let out = m[p]
    io.println(out == p)
    io.println(m.has(p))
}
