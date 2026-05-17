# STDOUT: 2
fun main() {
    let a = false
    let b = true
    let x = if a { 1 } else if b { 2 } else { 3 }
    print(x)
}
