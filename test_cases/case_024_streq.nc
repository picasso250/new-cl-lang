import io
# STDOUT: ok
fun main() {
    let a = "hello"
    let b = "hello"
    let c = "world"
    if a == b { io.println("ok") }
    if a == c { io.println("no") }
}
