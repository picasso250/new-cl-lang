# STDOUT: 2
# STDOUT: 1
# STDOUT: 0
# STDOUT: 0
# STDOUT: 0
import io

fun main() {
    let m = map[str,i32]{}
    m["a"] = 10
    m["b"] = 20
    io.println(len(m))
    delete(m, "a")
    io.println(len(m))
    io.println(m.has("a"))
    io.println(m["a"])
    clear(m)
    io.println(len(m))
}
