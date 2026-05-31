struct Box { value: i32 }
# ERROR: map value type: expected scalar, got Box

fun main() {
    let m = map[str,Box]()
}
