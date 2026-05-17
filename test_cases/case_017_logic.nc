# STDOUT: ok
# STDOUT: ok
# STDOUT: ok
fun main() {
    let a = true
    let b = true
    let c = false
    if a && b { print("ok") }
    if a || c { print("ok") }
    if !c { print("ok") }
}
