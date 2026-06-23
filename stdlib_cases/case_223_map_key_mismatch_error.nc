# ERROR: map key: expected i32, got str

fun main() {
    let m = map[i32,bool]{}
    m["x"] = true
}
