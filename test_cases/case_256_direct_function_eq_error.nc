# ERROR: comparison: type fun(i32) i32 is not comparable
fun main() {
    let a = fun(x: i32): i32 { x }
    let b = fun(x: i32): i32 { x }
    a == b
}
