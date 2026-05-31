# ERROR: map_has key: expected i32, got str

fun main() {
    let m = map[i32,bool]()
    map_has(m, "x")
}
