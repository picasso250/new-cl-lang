# ERROR: comparison: type []i32 is not comparable
fun main() {
    let a = []i32 { 1, 2 }
    let b = []i32 { 1, 2 }
    a == b
}
