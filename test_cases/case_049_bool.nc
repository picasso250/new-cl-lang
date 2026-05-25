import io
# STDOUT: 1
# STDOUT: 0
# STDOUT: ok
fun main() {
    let t: bool = true
    let f: bool = false
    io.println(t)
    io.println(f)
    if t && !f {
        io.println("ok")
    }
}
