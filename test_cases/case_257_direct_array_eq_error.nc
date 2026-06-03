# ERROR: comparison: type [2]i32 is not comparable
fun main() {
    let a = [2]i32 { 1, 2 }
    let b = [2]i32 { 1, 2 }
    a == b
}
