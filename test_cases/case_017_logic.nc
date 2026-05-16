# STDOUT: ok
# STDOUT: ok
# STDOUT: ok
fun main() {
    let a = 1
    let b = 1
    let c = 0
    if a && b { print("ok") }
    if a || c { print("ok") }
    if !c { print("ok") }
}
