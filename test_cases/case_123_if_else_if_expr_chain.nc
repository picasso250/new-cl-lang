# STDOUT: 3
fun main() {
    let a = false
    let b = false
    let x = if a { 1 } else if b { 2 } else { 3 }
    print(x)
}
