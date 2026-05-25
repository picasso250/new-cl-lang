import io
# STDOUT: ok
# STDOUT: ok
# STDOUT: ok
fun main() {
    let a = true
    let b = true
    let c = false
    if a && b { io.println("ok") }
    if a || c { io.println("ok") }
    if !c { io.println("ok") }
}
