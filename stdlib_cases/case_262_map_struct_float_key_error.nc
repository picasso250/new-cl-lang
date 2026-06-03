struct Key { x: f32 }
# ERROR: map key type: expected hash-comparable, got f32
fun main() {
    let m = map[Key,i32]()
}
