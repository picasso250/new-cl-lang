import io
# ERROR: for-in: expected slice or map, got str
fun main() {
    let s = "abc"
    for i, ch in s {
        io.println(ch)
    }
}
