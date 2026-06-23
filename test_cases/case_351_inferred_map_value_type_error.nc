# ERROR: map literal value: expected i32, got i64

fun main() {
    let _m = map{"a": 1, "b": i64(2)}
}
