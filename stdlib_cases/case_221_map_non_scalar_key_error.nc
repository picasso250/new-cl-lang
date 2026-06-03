struct Box { value: i32 }
# ERROR: map key type: expected hash-comparable, got []i32

fun main() {
    let m = map[[]i32,i32]()
}
