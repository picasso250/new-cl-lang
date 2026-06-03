# ERROR: comparison: type map[str,i32] is not comparable
fun main() {
    let a = map[str,i32]()
    let b = map[str,i32]()
    a == b
}
