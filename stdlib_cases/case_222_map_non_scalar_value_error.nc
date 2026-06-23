struct Box { value: i32 }
# ERROR: map value type: expected zero-value type, got *Box

fun main() {
    let m = map[str,*Box]{}
}
