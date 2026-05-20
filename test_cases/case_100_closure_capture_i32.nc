# STDOUT: 15
fun main() {
    let base = 10
    let add = fun(x: i32): i32 { x + base }
    print(add(5))
}
