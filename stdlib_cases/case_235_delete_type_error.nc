# ERROR: delete key: expected str, got i32
fun main() {
    let m = map[str,i32]{}
    delete(m, 1)
}
