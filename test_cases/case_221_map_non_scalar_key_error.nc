struct Box { value: i32 }
# ERROR: map key type: expected scalar, got Box

fun main() {
    let m = map[Box,i32]()
}
