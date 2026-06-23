# ERROR: argument 1 to method has: expected i32, got str

fun main() {
    let m = map[i32,bool]{}
    m.has("x")
}
