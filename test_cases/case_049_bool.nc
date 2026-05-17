# STDOUT: 1
# STDOUT: 0
# STDOUT: ok
fun main() {
    let t: bool = true
    let f: bool = false
    print(t)
    print(f)
    if t && !f {
        print("ok")
    }
}
